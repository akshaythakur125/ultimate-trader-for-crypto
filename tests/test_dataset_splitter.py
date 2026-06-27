from datetime import datetime, timedelta

import pytest

from ultimate_trader.validation_lab.dataset_splitter import (
    DatasetSplitter,
    InvalidSplitError,
)


class TestDatasetSplitter:
    def test_split_creates_non_overlapping_periods(self):
        splitter = DatasetSplitter()
        start = datetime(2023, 1, 1)
        end = datetime(2024, 1, 1)
        split = splitter.split(start, end)

        assert split.training_start < split.training_end < split.validation_start
        assert split.validation_start < split.validation_end < split.out_of_sample_start
        assert split.out_of_sample_start < split.out_of_sample_end

    def test_invalid_date_range_raises_error(self):
        splitter = DatasetSplitter()
        start = datetime(2024, 1, 1)
        end = datetime(2023, 1, 1)
        with pytest.raises(InvalidSplitError):
            splitter.split(start, end)

    def test_no_overlap(self):
        splitter = DatasetSplitter()
        start = datetime(2023, 1, 1)
        end = datetime(2024, 1, 1)
        split = splitter.split(start, end)
        assert splitter.validate_no_overlap(split)

    def test_creates_walk_forward_windows(self):
        splitter = DatasetSplitter()
        start = datetime(2023, 1, 1)
        end = datetime(2024, 1, 1)
        split = splitter.split(start, end, walk_forward_windows=3)
        assert len(split.walk_forward_windows) == 3

    def test_raises_on_excessive_ratios(self):
        splitter = DatasetSplitter()
        start = datetime(2023, 1, 1)
        end = datetime(2024, 1, 1)
        with pytest.raises(InvalidSplitError):
            splitter.split(start, end, training_ratio=0.8, validation_ratio=0.3)
