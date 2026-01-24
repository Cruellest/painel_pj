#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Worker local para treinamento BERT na GPU.

Este worker roda no PC local com GPU e:
1. Faz pull de jobs pendentes via API
2. Baixa o Excel do dataset
3. Executa o treinamento na GPU
4. Envia métricas e logs para a cloud

Uso:
    python bert_worker.py --api-url https://portal-pge.up.railway.app --token SEU_TOKEN
    python bert_worker.py --api-url http://localhost:8000 --token SEU_TOKEN --dry-run
"""

import argparse
import hashlib
import json
import logging
import os
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

import requests
import pandas as pd

# Configura logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bert_worker.log')
    ]
)
logger = logging.getLogger(__name__)


class BertWorker:
    """Worker local para treinamento BERT na GPU."""

    def __init__(
        self,
        api_url: str,
        token: str,
        models_dir: str = "./models",
        poll_interval: int = 30,
        dry_run: bool = False
    ):
        """
        Inicializa o worker.

        Args:
            api_url: URL base da API (ex: https://portal-pge.up.railway.app)
            token: Token de autenticação do worker
            models_dir: Diretório para salvar modelos treinados
            poll_interval: Intervalo entre verificações de jobs (segundos)
            dry_run: Se True, simula execução sem treinar
        """
        self.api_url = api_url.rstrip('/')
        self.token = token
        self.models_dir = Path(models_dir)
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.poll_interval = poll_interval
        self.dry_run = dry_run
        self.current_job_id: Optional[int] = None

    def _api_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        params: Optional[Dict] = None,
        stream: bool = False
    ) -> requests.Response:
        """Faz requisição para a API."""
        url = f"{self.api_url}/bert-training{endpoint}"

        if data and 'worker_token' not in data:
            data['worker_token'] = self.token

        try:
            response = requests.request(
                method=method,
                url=url,
                json=data,
                params=params,
                stream=stream,
                timeout=300 if not stream else None
            )
            return response
        except requests.exceptions.RequestException as e:
            logger.error(f"Erro na requisição {method} {endpoint}: {e}")
            raise

    def check_gpu(self) -> Dict[str, Any]:
        """Verifica disponibilidade da GPU."""
        try:
            import torch

            if not torch.cuda.is_available():
                return {'available': False, 'error': 'CUDA não disponível'}

            return {
                'available': True,
                'device_name': torch.cuda.get_device_name(0),
                'total_memory_gb': torch.cuda.get_device_properties(0).total_memory / 1e9,
                'cuda_version': torch.version.cuda
            }
        except ImportError:
            return {'available': False, 'error': 'PyTorch não instalado'}

    def send_heartbeat(self) -> bool:
        """Envia heartbeat para a API."""
        try:
            gpu_info = self.check_gpu()
            response = self._api_request(
                'POST',
                '/api/workers/heartbeat',
                data={
                    'worker_token': self.token,
                    'current_job_id': self.current_job_id,
                    'gpu_utilization': None,  # TODO: implementar monitoramento
                    'gpu_memory_used_gb': None
                }
            )
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"Falha ao enviar heartbeat: {e}")
            return False

    def claim_job(self) -> Optional[Dict]:
        """Tenta pegar um job da fila."""
        gpu_info = self.check_gpu()

        response = self._api_request(
            'POST',
            '/api/jobs/claim',
            data={
                'worker_token': self.token,
                'gpu_name': gpu_info.get('device_name'),
                'gpu_vram_gb': gpu_info.get('total_memory_gb'),
                'cuda_version': gpu_info.get('cuda_version')
            }
        )

        if response.status_code == 404:
            logger.debug("Nenhum job pendente")
            return None
        elif response.status_code == 200:
            job = response.json()
            logger.info(f"Job #{job['job_id']} claimed (run_id={job['run_id']})")
            return job
        else:
            logger.error(f"Erro ao clamar job: {response.status_code} - {response.text}")
            return None

    def download_dataset(self, download_url: str, expected_hash: str) -> Path:
        """Baixa o dataset e verifica integridade."""
        logger.info(f"Baixando dataset de {download_url}")

        # Constrói URL completa
        full_url = f"{self.api_url}{download_url}"
        response = requests.get(full_url, timeout=300)
        response.raise_for_status()

        # Salva em arquivo temporário
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as f:
            f.write(response.content)
            file_path = Path(f.name)

        # Verifica hash
        sha256_hash = hashlib.sha256(response.content).hexdigest()
        if sha256_hash != expected_hash:
            file_path.unlink()
            raise ValueError(f"Hash do dataset não confere. Esperado: {expected_hash}, Obtido: {sha256_hash}")

        logger.info(f"Dataset baixado e verificado: {file_path}")
        return file_path

    def update_progress(
        self,
        job_id: int,
        status: Optional[str] = None,
        current_epoch: Optional[int] = None,
        progress_percent: Optional[float] = None,
        error_message: Optional[str] = None
    ):
        """Atualiza progresso do job."""
        data = {'worker_token': self.token}

        if status:
            data['status'] = status
        if current_epoch is not None:
            data['current_epoch'] = current_epoch
        if progress_percent is not None:
            data['progress_percent'] = progress_percent
        if error_message:
            data['error_message'] = error_message

        try:
            self._api_request('POST', f'/api/jobs/{job_id}/progress', data=data)
        except Exception as e:
            logger.warning(f"Falha ao atualizar progresso: {e}")

    def send_metric(
        self,
        run_id: int,
        epoch: int,
        train_loss: Optional[float] = None,
        val_loss: Optional[float] = None,
        val_accuracy: Optional[float] = None,
        val_macro_f1: Optional[float] = None,
        val_weighted_f1: Optional[float] = None,
        classification_report: Optional[Dict] = None,
        confusion_matrix: Optional[List] = None
    ):
        """Envia métricas de uma época."""
        data = {
            'worker_token': self.token,
            'run_id': run_id,
            'epoch': epoch,
            'train_loss': train_loss,
            'val_loss': val_loss,
            'val_accuracy': val_accuracy,
            'val_macro_f1': val_macro_f1,
            'val_weighted_f1': val_weighted_f1,
            'classification_report': classification_report,
            'confusion_matrix': confusion_matrix
        }

        try:
            self._api_request('POST', '/api/metrics', data=data)
        except Exception as e:
            logger.warning(f"Falha ao enviar métrica: {e}")

    def send_log(
        self,
        run_id: int,
        level: str,
        message: str,
        epoch: Optional[int] = None,
        batch: Optional[int] = None
    ):
        """Envia log para a API."""
        data = {
            'worker_token': self.token,
            'run_id': run_id,
            'level': level,
            'message': message,
            'source': 'worker',
            'epoch': epoch,
            'batch': batch
        }

        try:
            self._api_request('POST', '/api/logs', data=data)
        except Exception as e:
            logger.warning(f"Falha ao enviar log: {e}")

    def complete_job(
        self,
        job_id: int,
        final_accuracy: float,
        final_macro_f1: float,
        final_weighted_f1: float,
        model_fingerprint: Optional[str] = None
    ):
        """Marca job como completo."""
        response = self._api_request(
            'POST',
            f'/api/jobs/{job_id}/complete',
            data={
                'worker_token': self.token,
                'final_accuracy': final_accuracy,
                'final_macro_f1': final_macro_f1,
                'final_weighted_f1': final_weighted_f1,
                'model_fingerprint': model_fingerprint
            }
        )

        if response.status_code == 200:
            logger.info(f"Job #{job_id} marcado como completo")
        else:
            logger.error(f"Erro ao completar job: {response.text}")

    def execute_training(self, job: Dict) -> bool:
        """
        Executa o treinamento de um job.

        Args:
            job: Dados do job (do endpoint /claim)

        Returns:
            True se sucesso, False se falhou
        """
        job_id = job['job_id']
        run_id = job['run_id']
        config = job['config']

        self.current_job_id = job_id
        self.send_log(run_id, 'INFO', f'Worker iniciou execução do job #{job_id}')

        # Dry run mode
        if self.dry_run:
            logger.info("[DRY RUN] Simulando treinamento...")
            self.update_progress(job_id, status='training', progress_percent=0)
            time.sleep(5)
            self.update_progress(job_id, status='training', current_epoch=1, progress_percent=50)
            time.sleep(5)
            self.complete_job(job_id, 0.85, 0.82, 0.84, "dry_run_fingerprint")
            return True

        # Verifica GPU
        gpu_info = self.check_gpu()
        if not gpu_info.get('available'):
            error_msg = f"GPU não disponível: {gpu_info.get('error')}"
            logger.error(error_msg)
            self.update_progress(job_id, status='failed', error_message=error_msg)
            self.send_log(run_id, 'ERROR', error_msg)
            return False

        self.send_log(run_id, 'INFO', f"GPU disponível: {gpu_info['device_name']}")

        try:
            # Atualiza status para downloading
            self.update_progress(job_id, status='downloading')

            # Baixa dataset
            dataset_path = self.download_dataset(
                job['dataset_download_url'],
                job['dataset_sha256']
            )
            self.send_log(run_id, 'INFO', f'Dataset baixado: {dataset_path}')

            # Carrega dataset
            df = pd.read_excel(dataset_path)
            self.send_log(run_id, 'INFO', f'Dataset carregado: {len(df)} amostras')

            # Atualiza status para training
            self.update_progress(job_id, status='training', progress_percent=0)

            # Imports do ML
            import torch
            from sistemas.bert_training.ml.classifier import BertClassifier
            from sistemas.bert_training.ml.dataset import prepare_data_from_dataframe
            from sistemas.bert_training.ml.training import Trainer, split_dataset
            from sistemas.bert_training.ml.evaluation import Evaluator

            device = 'cuda' if torch.cuda.is_available() else 'cpu'

            # Prepara dados
            task_type = job['task_type']
            full_dataset, label_to_id, id_to_label = prepare_data_from_dataframe(
                df=df,
                text_column=job['text_column'],
                label_column=job['label_column'],
                tokenizer_name=job['base_model'],
                max_length=config.get('max_length', 512),
                truncation_side=config.get('truncation_side', 'right'),
                task_type=task_type
            )

            # Split determinístico
            seed = config.get('seed', 42)
            train_split = config.get('train_split', 0.7)
            train_dataset, val_dataset = split_dataset(full_dataset, train_split, seed)

            self.send_log(
                run_id, 'INFO',
                f'Dataset dividido: {len(train_dataset)} treino, {len(val_dataset)} validação (seed={seed})'
            )

            # Cria modelo
            model = BertClassifier(
                model_name=job['base_model'],
                num_labels=len(label_to_id)
            )

            # Callback de progresso
            total_epochs = config.get('epochs', 10)

            def progress_callback(epoch_data):
                epoch = epoch_data['epoch']
                progress = (epoch / total_epochs) * 100

                self.update_progress(
                    job_id,
                    current_epoch=epoch,
                    progress_percent=progress
                )

                self.send_metric(
                    run_id=run_id,
                    epoch=epoch,
                    train_loss=epoch_data['train_loss'],
                    val_loss=epoch_data['val_loss'],
                    val_accuracy=epoch_data['val_accuracy']
                )

                self.send_log(
                    run_id, 'INFO',
                    f"Epoch {epoch}/{total_epochs}: Loss={epoch_data['train_loss']:.4f}, "
                    f"Val Acc={epoch_data['val_accuracy']:.4f}",
                    epoch=epoch
                )

            # Treina
            trainer = Trainer(
                model=model,
                train_dataset=train_dataset,
                val_dataset=val_dataset,
                device=device,
                batch_size=config.get('batch_size', 16),
                learning_rate=config.get('learning_rate', 5e-5),
                epochs=total_epochs,
                warmup_steps=config.get('warmup_steps', 0),
                weight_decay=config.get('weight_decay', 0.01),
                use_class_weights=config.get('use_class_weights', True),
                gradient_accumulation_steps=config.get('gradient_accumulation_steps', 1),
                early_stopping_patience=config.get('early_stopping_patience', 3),
                progress_callback=progress_callback
            )

            history = trainer.train()

            # Atualiza para evaluating
            self.update_progress(job_id, status='evaluating')
            self.send_log(run_id, 'INFO', 'Iniciando avaliação final')

            # Avalia
            evaluator = Evaluator(
                model=model,
                dataset=val_dataset,
                id_to_label=id_to_label,
                device=device
            )
            metrics = evaluator.evaluate()

            # Salva modelo localmente
            model_path = self.models_dir / f"model_run_{run_id}"
            fingerprint = model.save(model_path, id_to_label, job['base_model'])

            self.send_log(run_id, 'INFO', f'Modelo salvo em: {model_path}')
            self.send_log(run_id, 'INFO', f'Model fingerprint: {fingerprint}')

            # Envia métricas finais
            self.send_metric(
                run_id=run_id,
                epoch=len(history),
                val_accuracy=metrics['accuracy'],
                val_macro_f1=metrics['f1_score']['macro'],
                val_weighted_f1=metrics['f1_score']['weighted'],
                classification_report=metrics['classification_report'],
                confusion_matrix=metrics['confusion_matrix']
            )

            # Completa job
            self.complete_job(
                job_id,
                final_accuracy=metrics['accuracy'],
                final_macro_f1=metrics['f1_score']['macro'],
                final_weighted_f1=metrics['f1_score']['weighted'],
                model_fingerprint=fingerprint
            )

            self.send_log(run_id, 'INFO', 'Treinamento concluído com sucesso!')

            # Limpa arquivo temporário
            dataset_path.unlink(missing_ok=True)

            return True

        except Exception as e:
            error_msg = str(e)
            logger.exception(f"Erro no treinamento: {error_msg}")
            self.update_progress(job_id, status='failed', error_message=error_msg[:500])
            self.send_log(run_id, 'ERROR', f'Erro no treinamento: {error_msg}')
            return False

        finally:
            self.current_job_id = None

    def run(self):
        """Loop principal do worker."""
        logger.info(f"Iniciando worker BERT")
        logger.info(f"API URL: {self.api_url}")
        logger.info(f"Dry run: {self.dry_run}")

        # Verifica GPU no início
        gpu_info = self.check_gpu()
        if not gpu_info.get('available') and not self.dry_run:
            logger.error(f"GPU não disponível: {gpu_info.get('error')}")
            logger.error("Use --dry-run para simular execução sem GPU")
            sys.exit(1)

        logger.info(f"GPU: {gpu_info.get('device_name', 'N/A')}")

        # Envia heartbeat inicial
        if not self.send_heartbeat():
            logger.error("Falha ao conectar com a API. Verifique URL e token.")
            sys.exit(1)

        logger.info("Conectado à API. Aguardando jobs...")

        while True:
            try:
                # Envia heartbeat
                self.send_heartbeat()

                # Tenta pegar um job
                job = self.claim_job()

                if job:
                    success = self.execute_training(job)
                    if success:
                        logger.info("Job concluído com sucesso")
                    else:
                        logger.warning("Job falhou")
                else:
                    logger.debug(f"Aguardando {self.poll_interval}s...")

                time.sleep(self.poll_interval)

            except KeyboardInterrupt:
                logger.info("Worker interrompido pelo usuário")
                break
            except Exception as e:
                logger.exception(f"Erro no loop principal: {e}")
                time.sleep(self.poll_interval)


def main():
    parser = argparse.ArgumentParser(description='Worker BERT para treinamento local na GPU')

    parser.add_argument(
        '--api-url',
        required=True,
        help='URL base da API (ex: https://portal-pge.up.railway.app)'
    )

    parser.add_argument(
        '--token',
        required=True,
        help='Token de autenticação do worker'
    )

    parser.add_argument(
        '--models-dir',
        default='./bert_models',
        help='Diretório para salvar modelos treinados (default: ./bert_models)'
    )

    parser.add_argument(
        '--poll-interval',
        type=int,
        default=30,
        help='Intervalo entre verificações de jobs em segundos (default: 30)'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Simula execução sem treinar (para testes)'
    )

    parser.add_argument(
        '--debug',
        action='store_true',
        help='Ativa logs de debug'
    )

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    worker = BertWorker(
        api_url=args.api_url,
        token=args.token,
        models_dir=args.models_dir,
        poll_interval=args.poll_interval,
        dry_run=args.dry_run
    )

    worker.run()


if __name__ == '__main__':
    main()
