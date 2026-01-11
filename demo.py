#!/usr/bin/env python3
"""
Quick demo script - Submit sample tasks to Sentinel API.

Usage:
    python demo.py              # Submit 3 sample tasks
    python demo.py --count 5    # Submit 5 tasks
    python demo.py --watch      # Submit tasks and watch progress
"""

import argparse
import asyncio
import httpx
import sys
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.panel import Panel

console = Console()

BASE_URL = "http://localhost:8000"

# Sample tasks
SAMPLE_TASKS = [
    {
        "task_type": "research",
        "agent_type": "prompt-based",
        "tenant_id": "demo-tenant",
        "task_params": {
            "query": "Analyze the latest trends in AI agent orchestration",
            "max_steps": 3
        },
        "cost_limit": 2.0,
        "max_attempts": 3
    },
    {
        "task_type": "summarization",
        "agent_type": "prompt-based",
        "tenant_id": "demo-tenant",
        "task_params": {
            "query": "Summarize the key benefits of checkpoint-based task execution",
            "max_steps": 2
        },
        "cost_limit": 1.0,
        "max_attempts": 3
    },
    {
        "task_type": "analysis",
        "agent_type": "langgraph",
        "tenant_id": "demo-tenant",
        "task_params": {
            "query": "Compare different approaches to distributed task processing",
            "max_steps": 4
        },
        "cost_limit": 3.0,
        "max_attempts": 3
    }
]


async def check_api_health():
    """Check if API is accessible."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{BASE_URL}/health")
            if response.status_code == 200:
                data = response.json()
                return data.get("redis_connected", False)
            return False
    except Exception as e:
        console.print(f"[red]Failed to connect to API: {e}[/red]")
        return False


async def submit_task(task_data):
    """Submit a single task to the API."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(f"{BASE_URL}/tasks", json=task_data)
            
            if response.status_code == 201:
                return response.json()
            else:
                console.print(f"[red]Failed to create task: {response.status_code}[/red]")
                console.print(response.text)
                return None
    except Exception as e:
        console.print(f"[red]Error submitting task: {e}[/red]")
        return None


async def get_task_status(task_id):
    """Get current status of a task."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{BASE_URL}/tasks/{task_id}")
            if response.status_code == 200:
                return response.json()
            return None
    except Exception:
        return None


async def submit_demo_tasks(count=3):
    """Submit multiple demo tasks."""
    console.print("\n[bold cyan]Submitting demo tasks...[/bold cyan]\n")
    
    tasks = []
    for i in range(min(count, len(SAMPLE_TASKS))):
        task_data = SAMPLE_TASKS[i % len(SAMPLE_TASKS)].copy()
        task_data["task_params"]["query"] = f"[Demo {i+1}] " + task_data["task_params"]["query"]
        
        console.print(f"[yellow]Submitting task {i+1}/{count}...[/yellow]")
        result = await submit_task(task_data)
        
        if result:
            tasks.append(result)
            console.print(f"✓ Created task [cyan]{result['task_id']}[/cyan] - {result['task_type']}")
        else:
            console.print(f"✗ Failed to create task {i+1}")
        
        await asyncio.sleep(0.5)
    
    return tasks


async def watch_tasks(task_ids):
    """Watch task progress in real-time."""
    console.print("\n[bold cyan]Watching task progress...[/bold cyan]")
    console.print("[dim]Press Ctrl+C to stop[/dim]\n")
    
    completed = set()
    
    def create_status_table():
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Task ID", style="cyan", width=15)
        table.add_column("Type", style="green", width=15)
        table.add_column("Status", style="yellow", width=12)
        table.add_column("Cost", style="blue", width=10)
        table.add_column("Attempts", style="white", width=8)
        
        return table
    
    try:
        with Live(create_status_table(), refresh_per_second=2) as live:
            while len(completed) < len(task_ids):
                table = create_status_table()
                
                for task_id in task_ids:
                    status_data = await get_task_status(task_id)
                    
                    if status_data:
                        status = status_data.get("status", "unknown")
                        cost = status_data.get("cost_so_far", 0.0)
                        attempts = status_data.get("attempts", 0)
                        task_type = status_data.get("task_type", "unknown")
                        
                        # Color code status
                        if status == "completed":
                            status_display = f"[green]{status}[/green]"
                            completed.add(task_id)
                        elif status == "failed":
                            status_display = f"[red]{status}[/red]"
                            completed.add(task_id)
                        elif status == "leased":
                            status_display = f"[yellow]{status}[/yellow]"
                        else:
                            status_display = f"[dim]{status}[/dim]"
                        
                        table.add_row(
                            task_id[-12:],
                            task_type,
                            status_display,
                            f"${cost:.4f}",
                            str(attempts)
                        )
                    else:
                        table.add_row(task_id[-12:], "?", "[red]error[/red]", "?", "?")
                
                live.update(table)
                await asyncio.sleep(2)
    
    except KeyboardInterrupt:
        console.print("\n[yellow]Stopped watching[/yellow]")


async def show_final_summary(task_ids):
    """Show final summary of all tasks."""
    console.print("\n[bold cyan]Final Summary[/bold cyan]\n")
    
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Task ID", style="cyan")
    table.add_column("Type", style="green")
    table.add_column("Status", style="yellow")
    table.add_column("Cost", style="blue")
    table.add_column("Attempts", style="white")
    table.add_column("Duration", style="dim")
    
    total_cost = 0.0
    success_count = 0
    
    for task_id in task_ids:
        status_data = await get_task_status(task_id)
        
        if status_data:
            status = status_data.get("status", "unknown")
            cost = status_data.get("cost_so_far", 0.0)
            attempts = status_data.get("attempts", 0)
            task_type = status_data.get("task_type", "unknown")
            
            created = status_data.get("created_at", "")
            completed = status_data.get("completed_at", "")
            duration = "pending"
            
            if completed and created:
                try:
                    start = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    end = datetime.fromisoformat(completed.replace("Z", "+00:00"))
                    duration = f"{(end - start).total_seconds():.1f}s"
                except:
                    pass
            
            total_cost += cost
            if status == "completed":
                success_count += 1
                status = f"[green]{status}[/green]"
            elif status == "failed":
                status = f"[red]{status}[/red]"
            
            table.add_row(
                task_id[-12:],
                task_type,
                status,
                f"${cost:.4f}",
                str(attempts),
                duration
            )
    
    console.print(table)
    console.print(f"\n[bold]Total Cost:[/bold] ${total_cost:.4f}")
    console.print(f"[bold]Success Rate:[/bold] {success_count}/{len(task_ids)}")


async def main():
    parser = argparse.ArgumentParser(description="Sentinel Node Orchestrator Demo")
    parser.add_argument("--count", type=int, default=3, help="Number of tasks to submit")
    parser.add_argument("--watch", action="store_true", help="Watch task progress in real-time")
    parser.add_argument("--no-submit", action="store_true", help="Skip task submission (for testing)")
    args = parser.parse_args()
    
    # Header
    console.print(Panel.fit(
        "[bold cyan]Sentinel Node Orchestrator Demo[/bold cyan]\n"
        "Submitting sample tasks to showcase distributed execution",
        border_style="cyan"
    ))
    
    # Check API health
    console.print("\n[yellow]Checking API connection...[/yellow]")
    if not await check_api_health():
        console.print("[red]✗ API is not accessible or Redis is not connected[/red]")
        console.print("[dim]Make sure services are running: docker-compose up -d[/dim]")
        sys.exit(1)
    
    console.print("[green]✓ API is healthy and Redis is connected[/green]")
    
    if not args.no_submit:
        # Submit tasks
        tasks = await submit_demo_tasks(args.count)
        
        if not tasks:
            console.print("\n[red]No tasks were created[/red]")
            sys.exit(1)
        
        task_ids = [t["task_id"] for t in tasks]
        
        # Watch progress
        if args.watch:
            await watch_tasks(task_ids)
            await show_final_summary(task_ids)
        else:
            console.print("\n[green]✓ All tasks submitted successfully[/green]")
            console.print("\n[dim]To watch progress, run: python demo.py --watch[/dim]")
            console.print("[dim]To view in Grafana: http://localhost:3000[/dim]")
            console.print("[dim]To view traces: http://localhost:16686[/dim]")
    
    console.print("\n[bold green]Demo complete! 🚀[/bold green]\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Demo interrupted[/yellow]")
        sys.exit(0)
