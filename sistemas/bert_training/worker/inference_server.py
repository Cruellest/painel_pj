# -*- coding: utf-8 -*-
"""
Servidor de inferencia local para modelos BERT treinados.

Este servidor roda localmente e permite testar modelos treinados
via interface web do portal.

Uso:
    python -m sistemas.bert_training.worker.inference_server --models-dir ./models --port 8765
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Dict, Any, Optional
import hashlib

# Configura logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Tenta importar dependencias
try:
    from flask import Flask, request, jsonify
    from flask_cors import CORS
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False
    logger.warning("Flask nao instalado. Instale com: pip install flask flask-cors")

try:
    import torch
    from transformers import AutoTokenizer
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    logger.warning("PyTorch/Transformers nao instalado.")


# Cache de modelos carregados
loaded_models: Dict[str, Any] = {}


def load_model(model_path: Path) -> Optional[Dict[str, Any]]:
    """Carrega modelo do disco."""
    if not TORCH_AVAILABLE:
        return None

    checkpoint_path = model_path / "model.pt"
    if not checkpoint_path.exists():
        logger.error(f"Modelo nao encontrado: {checkpoint_path}")
        return None

    try:
        # Carrega checkpoint
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        # SECURITY: Bloqueia execução de código arbitrário durante o loading usando weights_only=True
        # Isso impede vulnerabilidades de desserialização insegura via pickle.
        try:
            checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=True)
        except TypeError:
            # Fallback para versões mais antigas do torch que não suportam weights_only
            logger.warning("weights_only=True não suportado nesta versão do torch. Use com cautela.")
            checkpoint = torch.load(checkpoint_path, map_location=device)

        # Carrega tokenizer
        base_model = checkpoint.get("base_model", "neuralmind/bert-base-portuguese-cased")
        tokenizer = AutoTokenizer.from_pretrained(base_model)

        # Recria o modelo
        from sistemas.bert_training.ml.classifier import BertClassifier

        id_to_label = checkpoint["id_to_label"]
        num_labels = len(id_to_label)

        model = BertClassifier(base_model, num_labels)
        model.load_state_dict(checkpoint["model_state_dict"])
        model.to(device)
        model.eval()

        logger.info(f"Modelo carregado: {model_path.name} ({num_labels} labels)")

        return {
            "model": model,
            "tokenizer": tokenizer,
            "id_to_label": id_to_label,
            "base_model": base_model,
            "device": device,
            "num_labels": num_labels
        }
    except Exception as e:
        logger.error(f"Erro ao carregar modelo {model_path}: {e}")
        return None


def predict_text(model_info: Dict[str, Any], text: str, max_length: int = 512) -> Dict[str, Any]:
    """Faz predicao para um texto."""
    model = model_info["model"]
    tokenizer = model_info["tokenizer"]
    id_to_label = model_info["id_to_label"]
    device = model_info["device"]

    # Tokeniza
    encoding = tokenizer(
        text,
        max_length=max_length,
        padding="max_length",
        truncation=True,
        return_tensors="pt"
    )

    input_ids = encoding["input_ids"].to(device)
    attention_mask = encoding["attention_mask"].to(device)
    token_type_ids = encoding.get("token_type_ids")
    if token_type_ids is not None:
        token_type_ids = token_type_ids.to(device)

    # Predicao
    with torch.no_grad():
        logits = model(input_ids, attention_mask, token_type_ids)
        probabilities = torch.softmax(logits, dim=-1)
        predicted_id = torch.argmax(probabilities, dim=-1).item()
        confidence = probabilities[0][predicted_id].item()

    predicted_label = id_to_label.get(predicted_id, str(predicted_id))

    return {
        "predicted_label": predicted_label,
        "confidence": round(confidence, 4),
        "all_probabilities": {
            id_to_label.get(i, str(i)): round(p.item(), 4)
            for i, p in enumerate(probabilities[0])
        }
    }


def create_app(models_dir: Path) -> Flask:
    """Cria aplicacao Flask."""
    app = Flask(__name__)
    CORS(app)  # Permite requests do navegador

    @app.route("/health", methods=["GET"])
    def health():
        """Health check."""
        return jsonify({
            "status": "ok",
            "torch_available": TORCH_AVAILABLE,
            "cuda_available": torch.cuda.is_available() if TORCH_AVAILABLE else False,
            "models_dir": str(models_dir)
        })

    @app.route("/models", methods=["GET"])
    def list_models():
        """Lista modelos disponiveis localmente."""
        models = []

        if not models_dir.exists():
            return jsonify({"models": [], "error": "Diretorio de modelos nao existe"})

        for model_path in models_dir.iterdir():
            if model_path.is_dir() and (model_path / "model.pt").exists():
                # Extrai run_id do nome da pasta
                run_id = None
                if model_path.name.startswith("model_run_"):
                    try:
                        run_id = int(model_path.name.replace("model_run_", ""))
                    except ValueError:
                        pass

                # Carrega info basica do modelo
                try:
                    checkpoint = torch.load(model_path / "model.pt", map_location="cpu")
                    id_to_label = checkpoint.get("id_to_label", {})
                    base_model = checkpoint.get("base_model", "unknown")

                    models.append({
                        "name": model_path.name,
                        "run_id": run_id,
                        "path": str(model_path),
                        "num_labels": len(id_to_label),
                        "labels": list(id_to_label.values()),
                        "base_model": base_model
                    })
                except Exception as e:
                    logger.warning(f"Erro ao ler info do modelo {model_path}: {e}")
                    models.append({
                        "name": model_path.name,
                        "run_id": run_id,
                        "path": str(model_path),
                        "error": str(e)
                    })

        return jsonify({"models": models})

    @app.route("/predict", methods=["POST"])
    def predict():
        """Faz predicao para texto."""
        if not TORCH_AVAILABLE:
            return jsonify({"error": "PyTorch nao disponivel"}), 500

        data = request.json
        if not data:
            return jsonify({"error": "Dados nao fornecidos"}), 400

        model_name = data.get("model")
        text = data.get("text")

        if not model_name or not text:
            return jsonify({"error": "model e text sao obrigatorios"}), 400

        # Carrega modelo (com cache)
        model_path = models_dir / model_name
        if model_name not in loaded_models:
            model_info = load_model(model_path)
            if not model_info:
                return jsonify({"error": f"Falha ao carregar modelo: {model_name}"}), 500
            loaded_models[model_name] = model_info

        model_info = loaded_models[model_name]

        # Faz predicao
        try:
            result = predict_text(model_info, text)
            return jsonify(result)
        except Exception as e:
            logger.error(f"Erro na predicao: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route("/predict/pdf", methods=["POST"])
    def predict_pdf():
        """Faz predicao para PDF (extrai texto e classifica)."""
        if not TORCH_AVAILABLE:
            return jsonify({"error": "PyTorch nao disponivel"}), 500

        if "file" not in request.files:
            return jsonify({"error": "Arquivo PDF nao enviado"}), 400

        model_name = request.form.get("model")
        if not model_name:
            return jsonify({"error": "model e obrigatorio"}), 400

        file = request.files["file"]

        # Extrai texto do PDF
        try:
            import fitz  # PyMuPDF
            pdf_bytes = file.read()
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            text = ""
            for page in doc:
                text += page.get_text()
            doc.close()
        except ImportError:
            return jsonify({"error": "PyMuPDF nao instalado. Instale com: pip install pymupdf"}), 500
        except Exception as e:
            return jsonify({"error": f"Erro ao ler PDF: {e}"}), 500

        if not text.strip():
            return jsonify({"error": "PDF sem texto extraivel"}), 400

        # Carrega modelo
        model_path = models_dir / model_name
        if model_name not in loaded_models:
            model_info = load_model(model_path)
            if not model_info:
                return jsonify({"error": f"Falha ao carregar modelo: {model_name}"}), 500
            loaded_models[model_name] = model_info

        model_info = loaded_models[model_name]

        # Faz predicao
        try:
            result = predict_text(model_info, text)
            result["extracted_text_length"] = len(text)
            result["filename"] = file.filename
            return jsonify(result)
        except Exception as e:
            logger.error(f"Erro na predicao: {e}")
            return jsonify({"error": str(e)}), 500

    return app


def main():
    parser = argparse.ArgumentParser(description="Servidor de inferencia BERT local")
    parser.add_argument("--models-dir", type=str, default="./models", help="Diretorio com modelos treinados")
    parser.add_argument("--port", type=int, default=8765, help="Porta do servidor")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host do servidor")
    args = parser.parse_args()

    if not FLASK_AVAILABLE:
        print("ERRO: Flask nao instalado. Instale com: pip install flask flask-cors")
        sys.exit(1)

    models_dir = Path(args.models_dir)
    if not models_dir.exists():
        print(f"Criando diretorio de modelos: {models_dir}")
        models_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"  Servidor de Inferencia BERT")
    print(f"{'='*60}")
    print(f"  Modelos: {models_dir.absolute()}")
    print(f"  URL: http://{args.host}:{args.port}")
    print(f"  CUDA: {'Disponivel' if (TORCH_AVAILABLE and torch.cuda.is_available()) else 'Nao disponivel'}")
    print(f"{'='*60}\n")

    app = create_app(models_dir)
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
