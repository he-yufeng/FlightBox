"""FlightBox CLI — inspect, replay, diff, and export recorded sessions."""

from __future__ import annotations

import json

import click
from rich.console import Console
from rich.table import Table

from flightbox.diff import diff_runs
from flightbox.export import export_jsonl, export_pytest
from flightbox.store import RecordStore

console = Console()


def _get_store(db: str | None) -> RecordStore:
    return RecordStore(db) if db else RecordStore()


@click.group()
@click.option("--db", default=None, help="Path to the SQLite database file.")
@click.pass_context
def cli(ctx, db):
    """FlightBox — Black-box flight recorder for AI agents."""
    ctx.ensure_object(dict)
    ctx.obj["db"] = db


@cli.command("list")
@click.option("-n", "--limit", default=20, help="Max runs to show.")
@click.pass_context
def list_runs(ctx, limit):
    """List recorded runs."""
    store = _get_store(ctx.obj["db"])
    runs = store.list_runs(limit)
    if not runs:
        console.print("[dim]No recordings found.[/dim]")
        return

    table = Table(title="Recorded Runs")
    table.add_column("Run ID", style="cyan")
    table.add_column("Name")
    table.add_column("Started")
    table.add_column("Events", justify="right")

    for r in runs:
        count = store.get_event_count(r["run_id"])
        table.add_row(
            r["run_id"],
            r.get("name") or "-",
            r["started_at"][:19],
            str(count),
        )
    console.print(table)
    store.close()


@cli.command("show")
@click.argument("run_id")
@click.pass_context
def show_run(ctx, run_id):
    """Show details of a recorded run."""
    store = _get_store(ctx.obj["db"])
    run = store.get_run(run_id)
    if not run:
        console.print(f"[red]Run '{run_id}' not found.[/red]")
        return

    console.print(f"[bold]Run:[/bold] {run['run_id']}")
    console.print(f"[bold]Name:[/bold] {run.get('name') or '-'}")
    console.print(f"[bold]Started:[/bold] {run['started_at']}")
    console.print(f"[bold]Finished:[/bold] {run.get('finished_at') or 'in progress'}")
    console.print()

    events = store.get_events(run_id)
    table = Table(title=f"Events ({len(events)} total)")
    table.add_column("#", justify="right", style="dim")
    table.add_column("Type")
    table.add_column("Provider")
    table.add_column("Model")
    table.add_column("Latency", justify="right")
    table.add_column("Tokens", justify="right")
    table.add_column("Error")

    for ev in events:
        usage = json.loads(ev["token_usage"]) if ev.get("token_usage") else {}
        total_tokens = (usage.get("prompt_tokens") or 0) + (usage.get("completion_tokens") or 0)
        table.add_row(
            str(ev["seq"]),
            ev["event_type"],
            ev.get("provider") or "-",
            ev.get("model") or "-",
            f"{ev['latency_ms']:.0f}ms" if ev.get("latency_ms") else "-",
            str(total_tokens) if total_tokens else "-",
            ev.get("error") or "",
        )
    console.print(table)
    store.close()


@cli.command("stats")
@click.argument("run_id")
@click.pass_context
def stats_cmd(ctx, run_id):
    """Show aggregate latency, token, and error stats for a run."""
    store = _get_store(ctx.obj["db"])
    run = store.get_run(run_id)
    if not run:
        console.print(f"[red]Run '{run_id}' not found.[/red]")
        return

    stats = store.get_run_stats(run_id)
    table = Table(title=f"Run Stats: {run_id}")
    table.add_column("Metric")
    table.add_column("Value", justify="right")

    rows = [
        ("Name", run.get("name") or "-"),
        ("Events", stats["events"]),
        ("LLM calls", stats["llm_calls"]),
        ("Errors", stats["errors"]),
        ("Prompt tokens", stats["prompt_tokens"]),
        ("Completion tokens", stats["completion_tokens"]),
        ("Total tokens", stats["total_tokens"]),
        ("Total latency", f"{stats['latency_ms_total']:.0f}ms"),
        ("Avg latency", f"{stats['latency_ms_avg']:.0f}ms"),
    ]
    for metric, value in rows:
        table.add_row(metric, str(value))

    console.print(table)
    store.close()


@cli.command("diff")
@click.argument("run_a")
@click.argument("run_b")
@click.pass_context
def diff_cmd(ctx, run_a, run_b):
    """Diff two recorded runs to find where they diverged."""
    store = _get_store(ctx.obj["db"])
    diffs = diff_runs(run_a, run_b, store)
    if not diffs:
        console.print("[green]Runs are identical.[/green]")
        return

    table = Table(title=f"Differences ({len(diffs)} found)")
    table.add_column("Step", justify="right")
    table.add_column("Field")
    table.add_column("Run A")
    table.add_column("Run B")

    for d in diffs[:50]:  # cap display
        a_str = _truncate(str(d.run_a_value), 60)
        b_str = _truncate(str(d.run_b_value), 60)
        table.add_row(str(d.seq), d.field, a_str, b_str)

    console.print(table)
    if len(diffs) > 50:
        console.print(f"[dim]... and {len(diffs) - 50} more differences[/dim]")
    store.close()


@cli.command("export")
@click.argument("run_id")
@click.option("-f", "--format", "fmt", type=click.Choice(["jsonl", "pytest"]), default="jsonl")
@click.option("-o", "--output", default=None, help="Output file path.")
@click.pass_context
def export_cmd(ctx, run_id, fmt, output):
    """Export a run as an eval dataset (JSONL) or pytest test."""
    store = _get_store(ctx.obj["db"])
    if fmt == "jsonl":
        out = output or f"flightbox_export_{run_id}.jsonl"
        count = export_jsonl(run_id, out, store)
        console.print(f"Exported {count} LLM calls to [bold]{out}[/bold]")
    else:
        out = output or f"test_replay_{run_id}.py"
        count = export_pytest(run_id, out, store)
        console.print(f"Generated pytest replay test with {count} events at [bold]{out}[/bold]")
    store.close()


@cli.command("delete")
@click.argument("run_id")
@click.confirmation_option(prompt="Delete this run?")
@click.pass_context
def delete_cmd(ctx, run_id):
    """Delete a recorded run."""
    store = _get_store(ctx.obj["db"])
    store.delete_run(run_id)
    console.print(f"[green]Deleted run {run_id}[/green]")
    store.close()


def _truncate(s: str, n: int) -> str:
    return s[:n] + "..." if len(s) > n else s
