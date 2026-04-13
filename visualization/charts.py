"""Price history chart generation using matplotlib."""

import logging
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def _import_matplotlib() -> tuple:
    """Lazy-import matplotlib with Agg backend.

    Raises ImportError with a helpful message if matplotlib is not installed.
    """
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.dates as mdates
        import matplotlib.pyplot as plt

        return plt, mdates
    except ImportError as err:
        raise ImportError(
            "matplotlib is required for chart generation. "
            "Install it with: pip install 'matplotlib>=3.8'"
        ) from err


def generate_price_chart(deal_id: str, session: Session, output_path: str | None = None) -> Path:
    """Generate a price history line chart for a specific deal.

    Args:
        deal_id: The deal ID to chart.
        session: SQLAlchemy Session instance.
        output_path: Optional path for the output PNG. Defaults to /tmp/price_chart_{deal_id}.png.

    Returns:
        Path to the generated PNG file.
    """
    from storage.repositories import DealRepository, PriceRepository

    plt, mdates = _import_matplotlib()

    deal_repo = DealRepository(session)
    price_repo = PriceRepository(session)

    deal = deal_repo.get_by_id(deal_id)
    if not deal:
        raise ValueError(f"Nie znaleziono oferty: {deal_id}")

    history = price_repo.get_history(deal_id)
    if not history:
        raise ValueError(f"Brak historii cen dla: {deal_id}")

    dates = [datetime.fromisoformat(h["recorded_at"]) for h in history]
    prices = [h["price"] for h in history]

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(dates, prices, marker="o", linewidth=2, color="#2196F3", markersize=5)

    # Mark lowest price with red dot
    min_price = min(prices)
    min_idx = prices.index(min_price)
    ax.plot(
        dates[min_idx],
        min_price,
        "ro",
        markersize=12,
        zorder=5,
        label=f"Najniższa: {min_price:,} PLN".replace(",", " "),
    )

    # Mark highest price with green dot
    max_price = max(prices)
    max_idx = prices.index(max_price)
    ax.plot(
        dates[max_idx],
        max_price,
        "go",
        markersize=12,
        zorder=5,
        label=f"Najwyższa: {max_price:,} PLN".replace(",", " "),
    )

    title = deal.get("title", deal_id)[:60]
    source = deal.get("source", "")
    ax.set_title(f"Historia cen: {title}\n({source})", fontsize=12, pad=10)
    ax.set_xlabel("Data")
    ax.set_ylabel("Cena (PLN)")
    ax.legend(loc="best")
    ax.grid(True, alpha=0.3)

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m"))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    fig.autofmt_xdate()

    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f"{int(x):,}".replace(",", " ")))

    plt.tight_layout()

    if output_path is None:
        safe_id = deal_id.replace(":", "_").replace("/", "_")
        output_path = str(Path(tempfile.gettempdir()) / f"price_chart_{safe_id}.png")

    path = Path(output_path)
    fig.savefig(str(path), dpi=150, bbox_inches="tight")
    plt.close(fig)

    logger.info(f"Price chart saved to {path}")
    return path


def generate_digest_chart(drops: list[dict], output_path: str | None = None) -> Path:
    """Generate a bar chart of the biggest price drops from the last week.

    Args:
        drops: List of price drop dicts (from PriceRepository.get_drops).
        output_path: Optional path for the output PNG.

    Returns:
        Path to the generated PNG file.
    """
    plt, mdates = _import_matplotlib()

    if not drops:
        raise ValueError("Brak danych o spadkach cen")

    # Top 10 biggest drops by percent
    sorted_drops = sorted(drops, key=lambda d: d["diff_percent"], reverse=True)[:10]

    titles = [d.get("title", "?")[:25] for d in sorted_drops]
    percents = [d["diff_percent"] for d in sorted_drops]

    colors = []
    for pct in percents:
        if pct > 20:
            colors.append("#F44336")  # red
        elif pct > 10:
            colors.append("#FF9800")  # orange
        else:
            colors.append("#FFC107")  # yellow

    fig, ax = plt.subplots(figsize=(10, 5))
    bars = ax.bar(range(len(titles)), percents, color=colors)

    ax.set_xticks(range(len(titles)))
    ax.set_xticklabels(titles, rotation=45, ha="right", fontsize=9)
    ax.set_ylabel("Spadek (%)")
    ax.set_title("Największe spadki cen (ostatni tydzień)", fontsize=12, pad=10)
    ax.grid(True, axis="y", alpha=0.3)

    # Add percentage labels on bars
    for bar, pct in zip(bars, percents, strict=False):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.5,
            f"-{pct:.0f}%",
            ha="center",
            va="bottom",
            fontsize=9,
            fontweight="bold",
        )

    plt.tight_layout()

    if output_path is None:
        output_path = str(Path(tempfile.gettempdir()) / "digest_chart.png")

    path = Path(output_path)
    fig.savefig(str(path), dpi=150, bbox_inches="tight")
    plt.close(fig)

    logger.info(f"Digest chart saved to {path}")
    return path


def generate_trend_chart(
    profile: str, session: Session, days: int = 30, output_path: str | None = None
) -> Path:
    """Generate a line chart showing average prices in a profile over the last N days.

    Args:
        profile: Profile name to chart.
        session: SQLAlchemy Session instance.
        days: Number of days to look back.
        output_path: Optional path for the output PNG.

    Returns:
        Path to the generated PNG file.
    """
    from storage.repositories import DealRepository, PriceRepository

    plt, mdates = _import_matplotlib()

    cutoff = (datetime.now() - timedelta(days=days)).isoformat()

    deal_repo = DealRepository(session)
    price_repo = PriceRepository(session)

    # Get all deals for this profile
    deals = deal_repo.get_filtered(profile=profile)
    if not deals:
        raise ValueError(f"Brak ofert dla profilu: {profile}")

    deal_ids = [d["id"] for d in deals]

    # Collect all price points within the date range (batch query — no N+1)
    daily_prices: dict[str, list[int]] = {}
    histories = price_repo.get_histories_batch(deal_ids)
    for deal_id in deal_ids:
        history = histories.get(deal_id, [])
        for h in history:
            if h["recorded_at"] < cutoff:
                continue
            date_str = h["recorded_at"][:10]  # YYYY-MM-DD
            daily_prices.setdefault(date_str, []).append(h["price"])

    if not daily_prices:
        raise ValueError(f"Brak danych cenowych dla profilu '{profile}' z ostatnich {days} dni")

    sorted_dates = sorted(daily_prices.keys())
    dates = [datetime.strptime(d, "%Y-%m-%d") for d in sorted_dates]
    avg_prices = [sum(daily_prices[d]) / len(daily_prices[d]) for d in sorted_dates]
    min_prices = [min(daily_prices[d]) for d in sorted_dates]
    max_prices = [max(daily_prices[d]) for d in sorted_dates]

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(
        dates,
        avg_prices,
        marker="o",
        linewidth=2,
        color="#2196F3",
        markersize=4,
        label="Średnia cena",
    )
    ax.fill_between(
        dates, min_prices, max_prices, alpha=0.15, color="#2196F3", label="Zakres (min–max)"
    )

    ax.set_title(f"Trend cenowy: {profile} (ostatnie {days} dni)", fontsize=12, pad=10)
    ax.set_xlabel("Data")
    ax.set_ylabel("Cena (PLN)")
    ax.legend(loc="best")
    ax.grid(True, alpha=0.3)

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m"))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    fig.autofmt_xdate()

    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f"{int(x):,}".replace(",", " ")))

    plt.tight_layout()

    if output_path is None:
        output_path = str(Path(tempfile.gettempdir()) / f"trend_chart_{profile}.png")

    path = Path(output_path)
    fig.savefig(str(path), dpi=150, bbox_inches="tight")
    plt.close(fig)

    logger.info(f"Trend chart saved to {path}")
    return path
