"""
Named Entity Recognition for Swedish text.

Uses KB-BERT fine-tuned for Swedish NER to extract:
- Person names (PER)
- Organizations (ORG)
- Locations (LOC)
- Swedish-specific entities (personnummer, organisationsnummer)
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from halo.config import settings
from halo.swedish.organisationsnummer import validate_organisationsnummer
from halo.swedish.personnummer import validate_personnummer

logger = logging.getLogger(__name__)


@dataclass
class Entity:
    """Extracted named entity."""

    text: str
    label: str  # PER, ORG, LOC, PERSONNUMMER, ORGNR, etc.
    start: int
    end: int
    confidence: float = 1.0
    normalized: Optional[str] = None
    metadata: dict = field(default_factory=dict)


class NamedEntityRecognizer:
    """
    Named Entity Recognition using KB-BERT.

    This class wraps the KB-BERT NER model for extracting entities
    from Swedish text. It also includes pattern-based extraction
    for Swedish identifiers (personnummer, organisationsnummer).
    """

    # Entity labels
    LABEL_PERSON = "PER"
    LABEL_ORG = "ORG"
    LABEL_LOCATION = "LOC"
    LABEL_PERSONNUMMER = "PERSONNUMMER"
    LABEL_ORGNR = "ORGNR"
    LABEL_PHONE = "PHONE"
    LABEL_EMAIL = "EMAIL"
    LABEL_MONEY = "MONEY"

    # Regex patterns for Swedish identifiers
    PERSONNUMMER_PATTERN = re.compile(
        r"\b(\d{6,8}[-+]?\d{4})\b"
    )
    ORGNR_PATTERN = re.compile(
        r"\b(16)?(\d{6}[-]?\d{4})\b"
    )
    PHONE_PATTERN = re.compile(
        r"\b(0\d{1,3}[-\s]?\d{2,3}[-\s]?\d{2,3}[-\s]?\d{2,4})\b"
    )
    EMAIL_PATTERN = re.compile(
        r"\b([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\b"
    )
    MONEY_PATTERN = re.compile(
        r"\b(\d{1,3}(?:[\s,]\d{3})*(?:[.,]\d{2})?)\s*(kr|sek|kronor|miljoner?|mdkr|mkr|tkr)\b",
        re.IGNORECASE,
    )

    def __init__(
        self,
        model_path: Optional[Path] = None,
        use_gpu: bool = False,
    ):
        """
        Initialize the NER system.

        Args:
            model_path: Path to KB-BERT NER model
            use_gpu: Whether to use GPU for inference
        """
        self.model_path = model_path or settings.kb_bert_model_path
        self.use_gpu = use_gpu
        self._model = None
        self._tokenizer = None
        self._model_loaded = False

    def _load_model(self):
        """
        Load the KB-BERT NER model.

        This is called lazily on first use to avoid loading
        the model if it's not needed.
        """
        if self._model_loaded:
            return

        try:
            from transformers import AutoModelForTokenClassification, AutoTokenizer

            logger.info(f"Loading KB-BERT NER model from {self.model_path}")

            # Try to load the model
            if self.model_path.exists():
                self._tokenizer = AutoTokenizer.from_pretrained(str(self.model_path))
                self._model = AutoModelForTokenClassification.from_pretrained(
                    str(self.model_path)
                )
            else:
                # Fall back to HuggingFace Hub
                model_name = "KB/bert-base-swedish-cased-ner"
                logger.info(f"Local model not found, using {model_name}")
                self._tokenizer = AutoTokenizer.from_pretrained(model_name)
                self._model = AutoModelForTokenClassification.from_pretrained(model_name)

            if self.use_gpu:
                import torch
                if torch.cuda.is_available():
                    self._model = self._model.cuda()

            self._model_loaded = True
            logger.info("KB-BERT NER model loaded successfully")

        except Exception as e:
            logger.warning(f"Could not load KB-BERT model: {e}. Using pattern-based NER only.")
            self._model_loaded = False

    def extract_entities(self, text: str) -> list[Entity]:
        """
        Extract named entities from text.

        Uses both pattern-based and ML-based extraction.

        Args:
            text: Input text

        Returns:
            List of extracted entities
        """
        entities = []

        # Pattern-based extraction (always works)
        entities.extend(self._extract_patterns(text))

        # ML-based extraction (if model available)
        if self._model is not None or not self._model_loaded:
            self._load_model()

        if self._model is not None:
            entities.extend(self._extract_with_model(text))

        # Deduplicate and sort by position
        entities = self._deduplicate(entities)
        entities.sort(key=lambda e: e.start)

        return entities

    def _extract_patterns(self, text: str) -> list[Entity]:
        """
        Extract entities using regex patterns.

        This catches Swedish identifiers that ML models might miss.
        """
        entities = []

        # Extract personnummer
        for match in self.PERSONNUMMER_PATTERN.finditer(text):
            pnr = match.group(1)
            info = validate_personnummer(pnr)
            if info.is_valid:
                entities.append(
                    Entity(
                        text=pnr,
                        label=self.LABEL_PERSONNUMMER,
                        start=match.start(1),
                        end=match.end(1),
                        confidence=1.0,
                        normalized=info.normalized,
                        metadata={
                            "birth_date": str(info.birth_date),
                            "gender": info.gender,
                            "is_coordination": info.is_coordination,
                        },
                    )
                )

        # Extract organisationsnummer
        for match in self.ORGNR_PATTERN.finditer(text):
            # Get the actual orgnr part (without optional 16 prefix)
            orgnr = match.group(2) if match.group(2) else match.group(0)
            info = validate_organisationsnummer(orgnr)
            if info.is_valid:
                entities.append(
                    Entity(
                        text=match.group(0),
                        label=self.LABEL_ORGNR,
                        start=match.start(),
                        end=match.end(),
                        confidence=1.0,
                        normalized=info.normalized,
                        metadata={
                            "organization_type": info.organization_type,
                        },
                    )
                )

        # Extract phone numbers
        for match in self.PHONE_PATTERN.finditer(text):
            entities.append(
                Entity(
                    text=match.group(1),
                    label=self.LABEL_PHONE,
                    start=match.start(1),
                    end=match.end(1),
                    confidence=0.9,
                )
            )

        # Extract email addresses
        for match in self.EMAIL_PATTERN.finditer(text):
            entities.append(
                Entity(
                    text=match.group(1),
                    label=self.LABEL_EMAIL,
                    start=match.start(1),
                    end=match.end(1),
                    confidence=0.95,
                )
            )

        # Extract money amounts
        for match in self.MONEY_PATTERN.finditer(text):
            entities.append(
                Entity(
                    text=match.group(0),
                    label=self.LABEL_MONEY,
                    start=match.start(),
                    end=match.end(),
                    confidence=0.9,
                    metadata={"currency": "SEK"},
                )
            )

        return entities

    def _extract_with_model(self, text: str) -> list[Entity]:
        """
        Extract entities using the KB-BERT NER model.
        """
        if self._model is None or self._tokenizer is None:
            return []

        try:
            import torch

            # Tokenize
            inputs = self._tokenizer(
                text,
                return_tensors="pt",
                return_offsets_mapping=True,
                truncation=True,
                max_length=512,
            )

            offset_mapping = inputs.pop("offset_mapping")[0]

            if self.use_gpu and torch.cuda.is_available():
                inputs = {k: v.cuda() for k, v in inputs.items()}

            # Get predictions
            with torch.no_grad():
                outputs = self._model(**inputs)

            predictions = torch.argmax(outputs.logits, dim=2)[0]
            scores = torch.softmax(outputs.logits, dim=2)[0]

            # Convert to entities
            entities = []
            current_entity = None
            label_map = self._model.config.id2label

            for idx, (pred, offset) in enumerate(zip(predictions, offset_mapping)):
                if offset[0] == offset[1]:  # Skip special tokens
                    continue

                label = label_map[pred.item()]
                score = scores[idx][pred].item()

                if label.startswith("B-"):
                    # Start of new entity
                    if current_entity:
                        entities.append(current_entity)
                    entity_type = label[2:]
                    current_entity = Entity(
                        text=text[offset[0] : offset[1]],
                        label=entity_type,
                        start=offset[0].item(),
                        end=offset[1].item(),
                        confidence=score,
                    )
                elif label.startswith("I-") and current_entity:
                    # Continuation of entity
                    entity_type = label[2:]
                    if entity_type == current_entity.label:
                        current_entity.text = text[current_entity.start : offset[1]]
                        current_entity.end = offset[1].item()
                        current_entity.confidence = min(current_entity.confidence, score)
                else:
                    # Outside entity
                    if current_entity:
                        entities.append(current_entity)
                        current_entity = None

            if current_entity:
                entities.append(current_entity)

            return entities

        except Exception as e:
            logger.error(f"Error in model-based NER: {e}")
            return []

    def _deduplicate(self, entities: list[Entity]) -> list[Entity]:
        """
        Remove duplicate entities.

        Prefers pattern-based matches (higher confidence) over ML-based.
        """
        if not entities:
            return []

        # Sort by position and confidence
        entities.sort(key=lambda e: (e.start, -e.confidence))

        deduplicated = []
        last_end = -1

        for entity in entities:
            # Skip if overlaps with previous entity
            if entity.start < last_end:
                continue

            deduplicated.append(entity)
            last_end = entity.end

        return deduplicated
