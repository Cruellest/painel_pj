# -*- coding: utf-8 -*-
"""
Classificador BERT para classificação de texto.

Adaptado do projeto E:\Projetos\BERT para integração com o portal PGE.
"""

import torch
import torch.nn as nn
from transformers import AutoModelForPreTraining, AutoTokenizer, AutoConfig
from typing import Optional, Tuple, Dict, Any
from pathlib import Path
import logging
import hashlib

logger = logging.getLogger(__name__)


class BertClassifier(nn.Module):
    """
    Classificador baseado em BERT para classificação de texto.
    Utiliza o token [CLS] como representação do texto.
    """

    def __init__(self, model_name: str, num_labels: int, dropout_prob: float = 0.1):
        """
        Inicializa o classificador.

        Args:
            model_name: Nome do modelo no Hugging Face Hub ou caminho local
            num_labels: Número de classes para classificação
            dropout_prob: Probabilidade de dropout
        """
        super(BertClassifier, self).__init__()

        self.model_name = model_name
        self.num_labels = num_labels

        # Carrega o modelo base
        logger.info(f"Carregando modelo base: {model_name}")
        base_model = AutoModelForPreTraining.from_pretrained(model_name)

        # Extrai apenas o encoder BERT
        self.bert = base_model.bert
        self.config = base_model.config

        # Camadas de classificação
        self.dropout = nn.Dropout(dropout_prob)
        self.classifier = nn.Linear(self.config.hidden_size, num_labels)

        logger.info(f"Classificador criado com {num_labels} classes")

    def forward(
        self,
        input_ids: Optional[torch.Tensor] = None,
        attention_mask: Optional[torch.Tensor] = None,
        token_type_ids: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        """
        Forward pass do modelo.

        Args:
            input_ids: IDs dos tokens
            attention_mask: Máscara de atenção
            token_type_ids: IDs de tipo de token

        Returns:
            Logits de classificação
        """
        outputs = self.bert(
            input_ids=input_ids,
            attention_mask=attention_mask,
            token_type_ids=token_type_ids,
        )

        # Usa o token [CLS] (primeiro token) como representação
        pooled_output = outputs[0][:, 0, :]
        pooled_output = self.dropout(pooled_output)
        logits = self.classifier(pooled_output)

        return logits

    def predict(
        self,
        input_ids: torch.Tensor,
        attention_mask: torch.Tensor,
        token_type_ids: Optional[torch.Tensor] = None
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Realiza predição com probabilidades.

        Returns:
            Tuple de (predições, probabilidades)
        """
        self.eval()
        with torch.no_grad():
            logits = self.forward(input_ids, attention_mask, token_type_ids)
            probabilities = torch.softmax(logits, dim=-1)
            predictions = torch.argmax(probabilities, dim=-1)

        return predictions, probabilities

    def save(
        self,
        path: Path,
        label_map: Dict[int, str],
        tokenizer_name: str,
        truncation_side: str = "right"
    ) -> str:
        """
        Salva o modelo treinado.

        Args:
            path: Diretório para salvar
            label_map: Mapeamento de índice para label
            tokenizer_name: Nome do tokenizer usado
            truncation_side: Lado do truncamento usado no treinamento

        Returns:
            Fingerprint (hash) do modelo salvo
        """
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)

        # Prepara dados para salvar
        checkpoint = {
            'model_state_dict': self.state_dict(),
            'num_labels': self.num_labels,
            'model_name': self.model_name,
            'label_map': label_map,
            'tokenizer_name': tokenizer_name,
            'truncation_side': truncation_side,
            'config': {
                'hidden_size': self.config.hidden_size,
                'dropout_prob': self.dropout.p
            }
        }

        model_path = path / 'model.pt'
        torch.save(checkpoint, model_path)

        # Calcula fingerprint do modelo
        fingerprint = self._calculate_fingerprint(model_path)

        logger.info(f"Modelo salvo em: {path}")
        logger.info(f"Model fingerprint: {fingerprint}")

        return fingerprint

    @staticmethod
    def _calculate_fingerprint(model_path: Path) -> str:
        """Calcula hash SHA256 do arquivo do modelo."""
        sha256_hash = hashlib.sha256()
        with open(model_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()[:16]

    @classmethod
    def load(
        cls,
        path: Path,
        device: str = 'cuda'
    ) -> Tuple['BertClassifier', Dict[int, str], str, str]:
        """
        Carrega um modelo salvo.

        Args:
            path: Diretório do modelo
            device: Dispositivo para carregar o modelo

        Returns:
            Tuple de (modelo, label_map, tokenizer_name, truncation_side)
        """
        path = Path(path)
        checkpoint = torch.load(path / 'model.pt', map_location=device)

        # Recria o modelo
        model = cls(
            model_name=checkpoint['model_name'],
            num_labels=checkpoint['num_labels'],
            dropout_prob=checkpoint['config']['dropout_prob']
        )

        model.load_state_dict(checkpoint['model_state_dict'])
        model.to(device)
        model.eval()

        # truncation_side pode não existir em modelos antigos
        truncation_side = checkpoint.get('truncation_side', 'right')

        logger.info(f"Modelo carregado de: {path}")

        return model, checkpoint['label_map'], checkpoint['tokenizer_name'], truncation_side


def verify_gpu_available() -> Dict[str, Any]:
    """
    Verifica disponibilidade da GPU.

    Returns:
        Dicionário com informações da GPU ou erro se não disponível
    """
    if not torch.cuda.is_available():
        return {
            'available': False,
            'error': 'CUDA não disponível'
        }

    return {
        'available': True,
        'device_name': torch.cuda.get_device_name(0),
        'total_memory_gb': torch.cuda.get_device_properties(0).total_memory / 1e9,
        'cuda_version': torch.version.cuda
    }
