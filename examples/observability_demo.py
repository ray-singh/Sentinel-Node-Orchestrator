"""
Demo: OpenTelemetry Tracing and Metrics

Shows how to use the observability features:
1. Start observability stack (Prometheus, Grafana, Jaeger)
2. Run API server with tracing enabled
3. Submit tasks and view traces/metrics
4. Query metrics in Prometheus
5. Visualize in Grafana dashboard

Prerequisites:
- Docker and Docker Compose installed
- Redis running (or use docker-compose.observability.yml)
- OPENAI_API_KEY set in environment
"""

import asyncio
import httpx
import time
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


async def demo_observability():
    """Demo OpenTelemetry tracing and Prometheus metrics."""
    
    console.print("\n[bold cyan]Sentinel Observability Demo[/bold cyan]\n")
    
    # Step 1: Instructions for starting observability stack
    console.print(Panel.fit(
        "[yellow]Step 1: Start Observability Stack[/yellow]\n\n"
        "Run in terminal:\n"
        "[green]docker-compose -f docker-compose.observability.yml up -d[/green]\n\n"
        "This starts:\n"
        "• Redis on port 6379\n"
        "• Prometheus on port 9090\n"
        "• Grafana on port 3000 (admin/admin)\n"
        "• Jaeger on port 16686",
        title="Setup"
    ))
    
    input("\nPress Enter when stack is running...")
    
    # Step 2: Start API server
    console.print(Panel.fit(
        "[yellow]Step 2: Start API Server[/yellow]\n\n"
        "In another terminal, run:\n"
        "[green]uvicorn src.api:app --host 0.0.0.0 --port 8000[/green]\n\n"
        "The API will automatically:\n"
        "• Initialize OpenTelemetry tracing\n"
        "• Instrument FastAPI endpoints\n"
        "• Export Prometheus metrics on port 9091\n"
        "• Send traces to Jaeger",
        title="API Server"
    ))
    
    input("\nPress Enter when API is running...")
    
    # Step 3: Submit test tasks
    console.print("\n[bold yellow]Step 3: Submitting Test Tasks[/bold yellow]\n")
    
    base_url = "http://localhost:8000"
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Create multiple tasks with different tenants
        tasks = []
        for i in range(3):
            tenant_id = f"tenant_{i}"
            
            try:
                response = await client.post(
                    f"{base_url}/tasks",
                    json={
                        "task_type": "analysis",
                        "agent_type": "prompt-based",
                        "task_params": {
                            "query": f"Analyze data for tenant {tenant_id}",
                            "max_steps": 5
                        },
                        "tenant_id": tenant_id,
                        "cost_limit": 1.0,
                        "max_attempts": 3
                    }
                )
                
                if response.status_code == 201:
                    task_data = response.json()
                    tasks.append(task_data)
                    console.print(f"✓ Created task [cyan]{task_data['task_id']}[/cyan] for [green]{tenant_id}[/green]")
                else:
                    console.print(f"✗ Failed to create task for {tenant_id}: {response.status_code}")
            
            except Exception as e:
                console.print(f"✗ Error creating task for {tenant_id}: {e}")
            
            # Small delay between requests
            await asyncio.sleep(0.5)
    
    console.print(f"\n[green]Created {len(tasks)} tasks[/green]")
    
    # Step 4: View metrics
    console.print("\n" + "="*70)
    console.print(Panel.fit(
        "[yellow]Step 4: View Metrics & Traces[/yellow]\n\n"
        "[bold cyan]Prometheus:[/bold cyan] http://localhost:9090\n"
        "Try these queries:\n"
        "• [green]sentinel_tasks_started_total[/green]\n"
        "• [green]sentinel_llm_cost_usd_total[/green]\n"
        "• [green]rate(sentinel_tasks_completed_total[5m])[/green]\n\n"
        "[bold cyan]Grafana:[/bold cyan] http://localhost:3000 (admin/admin)\n"
        "• Pre-loaded dashboard: 'Sentinel Node Orchestrator'\n"
        "• Shows task throughput, costs, latency\n\n"
        "[bold cyan]Jaeger:[/bold cyan] http://localhost:16686\n"
        "• Service: sentinel-orchestrator\n"
        "• Search by tenant_id, task_id, or llm_model\n"
        "• View distributed traces across workers",
        title="Access Dashboards"
    ))
    
    # Display sample Prometheus queries
    console.print("\n[bold cyan]Sample Prometheus Queries:[/bold cyan]\n")
    
    queries_table = Table(show_header=True, header_style="bold magenta")
    queries_table.add_column("Metric", style="cyan")
    queries_table.add_column("Query", style="green")
    queries_table.add_column("Description", style="white")
    
    queries_table.add_row(
        "Task Throughput",
        "rate(sentinel_tasks_completed_total[5m])",
        "Completed tasks per second"
    )
    queries_table.add_row(
        "LLM Cost/Hour",
        "rate(sentinel_llm_cost_usd_total[1h]) * 3600",
        "USD spent per hour by tenant"
    )
    queries_table.add_row(
        "Task Success Rate",
        "100 * sum(rate(sentinel_tasks_completed_total[5m])) / sum(rate(sentinel_tasks_started_total[5m]))",
        "Percentage of successful tasks"
    )
    queries_table.add_row(
        "Avg LLM Latency",
        "rate(sentinel_llm_latency_seconds_sum[5m]) / rate(sentinel_llm_latency_seconds_count[5m])",
        "Average LLM call duration"
    )
    queries_table.add_row(
        "Error Rate",
        "rate(sentinel_tasks_failed_total[5m]) / rate(sentinel_tasks_started_total[5m])",
        "Task failure percentage"
    )
    
    console.print(queries_table)
    
    # Metrics endpoints
    console.print("\n[bold cyan]Direct Metrics Access:[/bold cyan]")
    console.print("• Application metrics: [green]http://localhost:9091/metrics[/green]")
    console.print("• Prometheus metrics: [green]http://localhost:9090/api/v1/query[/green]")
    
    # Tracing examples
    console.print("\n[bold cyan]Tracing Examples:[/bold cyan]")
    console.print("1. Open Jaeger UI: [green]http://localhost:16686[/green]")
    console.print("2. Select service: [cyan]sentinel-orchestrator[/cyan]")
    console.print("3. Search by tags:")
    console.print("   • [yellow]tenant_id=tenant_0[/yellow]")
    console.print("   • [yellow]task_id=<task_id>[/yellow]")
    console.print("   • [yellow]llm_model=gpt-4o-mini[/yellow]")
    console.print("4. Click on a trace to view:")
    console.print("   • Span timeline (task → node → LLM)")
    console.print("   • Span attributes (tokens, cost, duration)")
    console.print("   • Logs and events")
    
    console.print("\n" + "="*70)
    console.print("\n[bold green]Demo Complete![/bold green]\n")
    console.print("Keep the services running and explore the dashboards.")
    console.print("Submit more tasks through the API to see real-time metrics.\n")


if __name__ == "__main__":
    try:
        asyncio.run(demo_observability())
    except KeyboardInterrupt:
        console.print("\n\n[yellow]Demo interrupted[/yellow]")
    except Exception as e:
        console.print(f"\n\n[red]Error: {e}[/red]")
