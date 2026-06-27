from datetime import datetime, timedelta
from typing import Optional

from pydantic import BaseModel, Field


class DatasetSplit(BaseModel):
    split_id: str
    training_start: datetime
    training_end: datetime
    validation_start: datetime
    validation_end: datetime
    out_of_sample_start: Optional[datetime] = None
    out_of_sample_end: Optional[datetime] = None
    walk_forward_windows: list[dict] = Field(default_factory=list)


class InvalidSplitError(ValueError):
    pass


class DatasetSplitter:
    def split(
        self,
        start_date: datetime,
        end_date: datetime,
        training_ratio: float = 0.6,
        validation_ratio: float = 0.2,
        walk_forward_windows: int = 3,
    ) -> DatasetSplit:
        total_days = (end_date - start_date).days

        if total_days <= 0:
            raise InvalidSplitError("End date must be after start date")

        if training_ratio + validation_ratio >= 1.0:
            raise InvalidSplitError("Training + validation ratio must be less than 1.0")

        training_days = int(total_days * training_ratio)
        validation_days = int(total_days * validation_ratio)

        training_start = start_date
        training_end = start_date + timedelta(days=training_days)
        validation_start = training_end + timedelta(days=1)
        validation_end = validation_start + timedelta(days=validation_days)
        oos_start = validation_end + timedelta(days=1)
        oos_end = end_date

        if oos_start >= oos_end:
            raise InvalidSplitError(
                "Out-of-sample period is empty, reduce training or validation ratio"
            )

        windows = self._create_walk_forward_windows(
            training_start, training_end, validation_start, validation_end, walk_forward_windows
        )

        return DatasetSplit(
            split_id="SPLIT-001",
            training_start=training_start,
            training_end=training_end,
            validation_start=validation_start,
            validation_end=validation_end,
            out_of_sample_start=oos_start,
            out_of_sample_end=oos_end,
            walk_forward_windows=windows,
        )

    def _create_walk_forward_windows(
        self,
        training_start: datetime,
        training_end: datetime,
        validation_start: datetime,
        validation_end: datetime,
        num_windows: int,
    ) -> list[dict]:
        train_days = (training_end - training_start).days
        val_days = (validation_end - validation_start).days

        if train_days <= 0 or val_days <= 0:
            return []

        window_size_train = train_days // num_windows
        window_size_val = val_days // num_windows

        windows = []
        for i in range(num_windows):
            windows.append({
                "window": i + 1,
                "train_start": (training_start + timedelta(days=i * window_size_train)).isoformat(),
                "train_end": (training_start + timedelta(days=(i + 1) * window_size_train)).isoformat(),
                "val_start": (validation_start + timedelta(days=i * window_size_val)).isoformat(),
                "val_end": (validation_start + timedelta(days=(i + 1) * window_size_val)).isoformat(),
            })

        return windows

    def validate_no_overlap(self, split: DatasetSplit) -> bool:
        if split.training_end >= split.validation_start:
            return False
        if split.validation_end >= split.out_of_sample_start:
            return False
        if split.training_end >= split.out_of_sample_start:
            return False
        return True
