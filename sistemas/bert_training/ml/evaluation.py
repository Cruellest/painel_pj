# -*- coding: utf-8 -*-
"""
Avaliação e métricas do modelo BERT.

Adaptado do projeto E:\Projetos\BERT para integração com o portal PGE.
"""

import torch
from torch.utils.data import DataLoader
from typing import Dict, List, Any, Tuple, Optional
import numpy as np
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    classification_report,
    confusion_matrix
)
import logging

from sistemas.bert_training.ml.classifier import BertClassifier

logger = logging.getLogger(__name__)


class Evaluator:
    """
    Avaliador de modelos de classificação.
    """

    def __init__(
        self,
        model: BertClassifier,
        dataset,
        id_to_label: Dict[int, str],
        device: str = 'cuda',
        batch_size: int = 16,
        texts: Optional[List[str]] = None
    ):
        """
        Inicializa o avaliador.

        Args:
            model: Modelo treinado
            dataset: Dataset de teste
            id_to_label: Mapeamento de índice para label
            device: Dispositivo
            batch_size: Tamanho do batch
            texts: Lista de textos originais (para análise de erros)
        """
        self.model = model.to(device)
        self.model.eval()
        self.device = device
        self.id_to_label = id_to_label
        self.labels = [id_to_label[i] for i in range(len(id_to_label))]
        self.texts = texts

        self.dataloader = DataLoader(
            dataset,
            batch_size=batch_size,
            shuffle=False,
            num_workers=0
        )

    def get_predictions(self) -> Tuple[List[int], List[int], np.ndarray]:
        """
        Obtém predições do modelo.

        Returns:
            Tuple de (y_true, y_pred, probabilities)
        """
        all_predictions = []
        all_labels = []
        all_probabilities = []

        with torch.no_grad():
            for batch in self.dataloader:
                input_ids = batch['input_ids'].to(self.device)
                attention_mask = batch['attention_mask'].to(self.device)
                labels = batch['labels'].to(self.device)

                token_type_ids = None
                if 'token_type_ids' in batch:
                    token_type_ids = batch['token_type_ids'].to(self.device)

                logits = self.model(input_ids, attention_mask, token_type_ids)
                probabilities = torch.softmax(logits, dim=-1)
                predictions = torch.argmax(logits, dim=-1)

                all_predictions.extend(predictions.cpu().numpy())
                all_labels.extend(labels.cpu().numpy())
                all_probabilities.extend(probabilities.cpu().numpy())

        return all_labels, all_predictions, np.array(all_probabilities)

    def get_misclassified(self) -> List[Dict[str, Any]]:
        """
        Obtém lista de textos classificados incorretamente.

        Returns:
            Lista de dicionários com detalhes dos erros
        """
        y_true, y_pred, probabilities = self.get_predictions()

        misclassified = []
        for i, (true_label, pred_label, probs) in enumerate(zip(y_true, y_pred, probabilities)):
            if true_label != pred_label:
                text = self.texts[i] if self.texts and i < len(self.texts) else f"[Texto #{i}]"
                misclassified.append({
                    'index': i,
                    'text': str(text),
                    'true_label': self.id_to_label[true_label],
                    'predicted_label': self.id_to_label[pred_label],
                    'confidence': float(probs[pred_label]),
                    'true_label_prob': float(probs[true_label])
                })

        return misclassified

    def evaluate(self, save_errors: bool = True) -> Dict[str, Any]:
        """
        Avalia o modelo e retorna métricas completas.

        Args:
            save_errors: Se deve incluir lista de erros no resultado

        Returns:
            Dicionário com todas as métricas
        """
        logger.info("Iniciando avaliação do modelo...")

        y_true, y_pred, probabilities = self.get_predictions()

        # Métricas gerais
        accuracy = accuracy_score(y_true, y_pred)

        # Precision
        macro_precision = precision_score(y_true, y_pred, average='macro', zero_division=0)
        micro_precision = precision_score(y_true, y_pred, average='micro', zero_division=0)
        weighted_precision = precision_score(y_true, y_pred, average='weighted', zero_division=0)

        # Recall
        macro_recall = recall_score(y_true, y_pred, average='macro', zero_division=0)
        micro_recall = recall_score(y_true, y_pred, average='micro', zero_division=0)
        weighted_recall = recall_score(y_true, y_pred, average='weighted', zero_division=0)

        # F1-Score
        macro_f1 = f1_score(y_true, y_pred, average='macro', zero_division=0)
        micro_f1 = f1_score(y_true, y_pred, average='micro', zero_division=0)
        weighted_f1 = f1_score(y_true, y_pred, average='weighted', zero_division=0)

        # Classification report
        all_labels = list(range(len(self.labels)))
        report = classification_report(
            y_true, y_pred,
            labels=all_labels,
            target_names=self.labels,
            output_dict=True,
            zero_division=0
        )

        # Confusion matrix
        cm = confusion_matrix(y_true, y_pred, labels=all_labels)

        # Detalhes dos erros por célula da matriz
        error_details = {}
        if self.texts:
            for i, (true_label, pred_label, probs) in enumerate(zip(y_true, y_pred, probabilities)):
                if true_label != pred_label:
                    key = f"{self.id_to_label[true_label]}|{self.id_to_label[pred_label]}"
                    if key not in error_details:
                        error_details[key] = []

                    text = self.texts[i] if i < len(self.texts) else f"[Texto #{i}]"
                    error_details[key].append({
                        'index': i,
                        'text': str(text),
                        'confidence': float(probs[pred_label]),
                        'true_label_prob': float(probs[true_label])
                    })

        metrics = {
            'accuracy': float(accuracy),
            'precision': {
                'macro': float(macro_precision),
                'micro': float(micro_precision),
                'weighted': float(weighted_precision)
            },
            'recall': {
                'macro': float(macro_recall),
                'micro': float(micro_recall),
                'weighted': float(weighted_recall)
            },
            'f1_score': {
                'macro': float(macro_f1),
                'micro': float(micro_f1),
                'weighted': float(weighted_f1)
            },
            'classification_report': report,
            'confusion_matrix': cm.tolist(),
            'labels': self.labels,
            'error_details': error_details
        }

        logger.info(f"Avaliação concluída - Accuracy: {accuracy:.4f}, Macro F1: {macro_f1:.4f}")
        logger.info(f"Total de erros: {len([1 for t, p in zip(y_true, y_pred) if t != p])}")

        return metrics


def format_metrics_summary(metrics: Dict[str, Any]) -> str:
    """
    Formata um resumo das métricas para log.

    Args:
        metrics: Dicionário de métricas

    Returns:
        String formatada
    """
    summary = f"""
{'='*60}
RESULTADOS DA AVALIAÇÃO
{'='*60}

Accuracy: {metrics['accuracy']:.4f}

Precision:
  - Macro:    {metrics['precision']['macro']:.4f}
  - Micro:    {metrics['precision']['micro']:.4f}
  - Weighted: {metrics['precision']['weighted']:.4f}

Recall:
  - Macro:    {metrics['recall']['macro']:.4f}
  - Micro:    {metrics['recall']['micro']:.4f}
  - Weighted: {metrics['recall']['weighted']:.4f}

F1-Score:
  - Macro:    {metrics['f1_score']['macro']:.4f}
  - Micro:    {metrics['f1_score']['micro']:.4f}
  - Weighted: {metrics['f1_score']['weighted']:.4f}

{'='*60}
"""
    return summary


try:
    from seqeval.metrics import f1_score as seqeval_f1
    from seqeval.metrics import precision_score as seqeval_precision
    from seqeval.metrics import recall_score as seqeval_recall

    def evaluate_ner(y_true: List[List[str]], y_pred: List[List[str]]) -> Dict[str, float]:
        """
        Avalia modelo NER usando seqeval.

        Args:
            y_true: Lista de listas de tags verdadeiras
            y_pred: Lista de listas de tags preditas

        Returns:
            Dicionário com métricas seqeval
        """
        return {
            'seqeval_f1': seqeval_f1(y_true, y_pred),
            'seqeval_precision': seqeval_precision(y_true, y_pred),
            'seqeval_recall': seqeval_recall(y_true, y_pred)
        }

except ImportError:
    def evaluate_ner(y_true, y_pred):
        """seqeval não disponível."""
        logger.warning("seqeval não instalado, métricas NER não disponíveis")
        return {}
