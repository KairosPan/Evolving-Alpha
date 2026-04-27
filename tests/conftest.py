import pytest
from unittest.mock import MagicMock
from tests.fixtures.synthetic.build_synthetic import build_warming_day


@pytest.fixture
def synthetic_warming():
    return build_warming_day("2026-04-25")


@pytest.fixture
def mock_akshare_client(synthetic_warming):
    cli = MagicMock()
    data = synthetic_warming
    cli.limit_up_pool.side_effect = lambda d: data["ztb_today"] if d == "2026-04-25" else data["ztb_yesterday"]
    cli.blast_pool.return_value = data["blast"]
    cli.index_daily.return_value = data["idx_sh"]
    cli.market_activity.return_value = data["activity"]
    return cli
