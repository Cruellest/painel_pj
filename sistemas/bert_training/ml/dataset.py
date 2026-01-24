# -*- coding: utf-8 -*-
"""
Dataset PyTorch para classificação de texto.

Adaptado do projeto E:\Projetos\BERT para integração com o portal PGE.
"""

import json
import torch
from torch.utils.data import Dataset
from transformers import AutoTokenizer
from typing import List, Dict, Optional, Tuple
import pandas as pd
import logging

logger = logging.getLogger(__name__)


class TextClassificationDataset(Dataset):
    """
    Dataset PyTorch para classificação de texto com BERT.
    """

    def __init__(
        self,
        texts: List[str],
        labels: Optional[List[int]] = None,
        tokenizer_name: str = "neuralmind/bert-base-portuguese-cased",
        max_length: int = 512,
        truncation_side: str = "right"
    ):
        """
        Inicializa o dataset.

        Args:
            texts: Lista de textos
            labels: Lista de labels (opcional para inferência)
            tokenizer_name: Nome do tokenizer do Hugging Face
            max_length: Tamanho máximo da sequência
            truncation_side: Lado do truncamento ('right' = primeiros tokens, 'left' = últimos tokens)
        """
        self.texts = texts
        self.labels = labels
        self.max_length = max_length
        self.truncation_side = truncation_side

        # Carrega o tokenizer
        logger.info(f"Carregando tokenizer: {tokenizer_name}")
        self.tokenizer = AutoTokenizer.from_pretrained(tokenizer_name)
        # Configura o lado do truncamento
        self.tokenizer.truncation_side = truncation_side
        logger.info(
            f"Truncamento configurado: {truncation_side} "
            f"(mantém {'primeiros' if truncation_side == 'right' else 'últimos'} {max_length} tokens)"
        )

        # Log de debug para primeiro texto longo
        if texts and len(texts) > 0:
            sample_text = str(texts[0])
            tokens_full = self.tokenizer.tokenize(sample_text)
            if len(tokens_full) > max_length:
                logger.info(f"[DEBUG TRUNCAMENTO] Texto original tem {len(tokens_full)} tokens")

    def __len__(self) -> int:
        return len(self.texts)

    def __getitem__(self, idx: int) -> Dict[str, torch.Tensor]:
        text = str(self.texts[idx])

        # Tokenização
        encoding = self.tokenizer(
            text,
            add_special_tokens=True,
            max_length=self.max_length,
            padding='max_length',
            truncation=True,
            return_attention_mask=True,
            return_tensors='pt'
        )

        item = {
            'input_ids': encoding['input_ids'].flatten(),
            'attention_mask': encoding['attention_mask'].flatten(),
        }

        # Adiciona token_type_ids se disponível
        if 'token_type_ids' in encoding:
            item['token_type_ids'] = encoding['token_type_ids'].flatten()

        # Adiciona label se disponível
        if self.labels is not None:
            item['labels'] = torch.tensor(self.labels[idx], dtype=torch.long)

        return item


class TokenClassificationDataset(Dataset):
    """
    Dataset PyTorch para classificação de tokens (NER/BIO).
    """

    def __init__(
        self,
        tokens_list: List[List[str]],
        tags_list: Optional[List[List[str]]] = None,
        tokenizer_name: str = "neuralmind/bert-base-portuguese-cased",
        max_length: int = 512,
        label_to_id: Optional[Dict[str, int]] = None
    ):
        """
        Inicializa o dataset.

        Args:
            tokens_list: Lista de listas de tokens
            tags_list: Lista de listas de tags (opcional para inferência)
            tokenizer_name: Nome do tokenizer do Hugging Face
            max_length: Tamanho máximo da sequência
            label_to_id: Mapeamento de label para índice
        """
        self.tokens_list = tokens_list
        self.tags_list = tags_list
        self.max_length = max_length
        self.label_to_id = label_to_id or {}

        # Carrega o tokenizer
        logger.info(f"Carregando tokenizer: {tokenizer_name}")
        self.tokenizer = AutoTokenizer.from_pretrained(tokenizer_name)

    def __len__(self) -> int:
        return len(self.tokens_list)

    def __getitem__(self, idx: int) -> Dict[str, torch.Tensor]:
        tokens = self.tokens_list[idx]
        tags = self.tags_list[idx] if self.tags_list else None

        # Tokeniza preservando alinhamento de palavras
        encoding = self.tokenizer(
            tokens,
            is_split_into_words=True,
            add_special_tokens=True,
            max_length=self.max_length,
            padding='max_length',
            truncation=True,
            return_attention_mask=True,
            return_tensors='pt'
        )

        item = {
            'input_ids': encoding['input_ids'].flatten(),
            'attention_mask': encoding['attention_mask'].flatten(),
        }

        if 'token_type_ids' in encoding:
            item['token_type_ids'] = encoding['token_type_ids'].flatten()

        # Alinha tags com tokens do subword
        if tags:
            word_ids = encoding.word_ids()
            label_ids = []
            previous_word_idx = None

            for word_idx in word_ids:
                if word_idx is None:
                    label_ids.append(-100)  # Tokens especiais
                elif word_idx != previous_word_idx:
                    # Primeiro subword do token original
                    if word_idx < len(tags):
                        label_ids.append(self.label_to_id.get(tags[word_idx], 0))
                    else:
                        label_ids.append(-100)
                else:
                    # Subwords seguintes: usa -100 para ignorar na loss
                    label_ids.append(-100)

                previous_word_idx = word_idx

            item['labels'] = torch.tensor(label_ids, dtype=torch.long)

        return item


def create_label_encoder(labels: List[str]) -> Tuple[Dict[str, int], Dict[int, str]]:
    """
    Cria mapeamentos de label para índice e vice-versa.

    Args:
        labels: Lista de labels únicas

    Returns:
        Tuple de (label_to_id, id_to_label)
    """
    unique_labels = sorted(set(labels))
    label_to_id = {label: idx for idx, label in enumerate(unique_labels)}
    id_to_label = {idx: label for label, idx in label_to_id.items()}

    return label_to_id, id_to_label


def prepare_data_from_dataframe(
    df: pd.DataFrame,
    text_column: str,
    label_column: str,
    tokenizer_name: str = "neuralmind/bert-base-portuguese-cased",
    max_length: int = 512,
    truncation_side: str = "right",
    task_type: str = "text_classification"
) -> Tuple[Dataset, Dict[str, int], Dict[int, str]]:
    """
    Prepara os dados a partir de um DataFrame.

    Args:
        df: DataFrame com os dados
        text_column: Nome da coluna de texto
        label_column: Nome da coluna de label
        tokenizer_name: Nome do tokenizer
        max_length: Tamanho máximo da sequência
        truncation_side: Lado do truncamento
        task_type: Tipo de tarefa ('text_classification' ou 'token_classification')

    Returns:
        Tuple de (dataset, label_to_id, id_to_label)
    """
    if task_type == "text_classification":
        texts = df[text_column].tolist()
        labels_str = df[label_column].tolist()

        # Cria o encoder de labels
        label_to_id, id_to_label = create_label_encoder(labels_str)

        # Converte labels para índices
        labels = [label_to_id[label] for label in labels_str]

        # Cria o dataset
        dataset = TextClassificationDataset(
            texts=texts,
            labels=labels,
            tokenizer_name=tokenizer_name,
            max_length=max_length,
            truncation_side=truncation_side
        )

    else:  # token_classification
        # Parseia tokens e tags de JSON
        tokens_list = []
        tags_list = []

        for idx, row in df.iterrows():
            tokens = row[text_column]
            tags = row[label_column]

            # Parse JSON se necessário
            if isinstance(tokens, str):
                tokens = json.loads(tokens)
            if isinstance(tags, str):
                tags = json.loads(tags)

            tokens_list.append(tokens)
            tags_list.append(tags)

        # Coleta todas as tags únicas
        all_tags = set()
        for tags in tags_list:
            all_tags.update(tags)

        label_to_id, id_to_label = create_label_encoder(list(all_tags))

        # Cria o dataset
        dataset = TokenClassificationDataset(
            tokens_list=tokens_list,
            tags_list=tags_list,
            tokenizer_name=tokenizer_name,
            max_length=max_length,
            label_to_id=label_to_id
        )

    logger.info(f"Dataset criado com {len(dataset)} amostras e {len(label_to_id)} classes")

    return dataset, label_to_id, id_to_label
