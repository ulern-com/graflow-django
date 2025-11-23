import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

# Import graflow graphs to ensure they are registered
# The import itself is needed to trigger registration, even if not directly used
import graflow.graphs  # noqa: F401
from graflow.graphs.registry import _GRAPH_REGISTRY, _LATEST_VERSIONS, get_graph


class Command(BaseCommand):
    help = "Visualize a registered graph using LangGraph's built-in visualization"

    def add_arguments(self, parser):
        parser.add_argument(
            "--graph-name",
            type=str,
            help="Name of the graph to visualize (e.g., 'workflow_a', 'process_b')",
        )
        parser.add_argument(
            "--graph-version",
            type=str,
            help="Version of the graph (defaults to latest)",
        )
        parser.add_argument(
            "--app-name",
            type=str,
            default="ulern",
            help="Application name (default: ulern)",
        )
        parser.add_argument(
            "--output-dir",
            type=str,
            help=(
                "Output directory for the visualization "
                "(defaults to MEDIA_ROOT/graph_visualizations)"
            ),
        )
        parser.add_argument(
            "--list",
            action="store_true",
            help="List all available graphs",
        )
        parser.add_argument(
            "--format",
            type=str,
            choices=["png", "ascii"],
            default="png",
            help="Output format: png for Mermaid diagram, ascii for terminal output (default: png)",
        )

    def handle(self, *args, **options):
        if options["list"]:
            self.list_available_graphs()
            return

        graph_name = options["graph_name"]
        if not graph_name:
            raise CommandError("Please specify --graph-name or use --list to see available graphs")

        try:
            # Get the graph
            graph = get_graph(graph_name, options["graph_version"], options["app_name"])
            if not graph:
                raise CommandError(f"Graph '{graph_name}' not found")

            # Create output directory
            # Use getattr with default to safely access settings
            media_root = getattr(settings, "MEDIA_ROOT", "./media")
            output_dir = options["output_dir"] or os.path.join(media_root, "graph_visualizations")
            os.makedirs(output_dir, exist_ok=True)

            # Create visualization using LangGraph's built-in methods
            output_path = self.create_visualization(
                graph,
                graph_name,
                options["graph_version"] or _LATEST_VERSIONS.get((options["app_name"], graph_name)),
                output_dir,
                options["format"],
            )

            self.stdout.write(self.style.SUCCESS(f"Graph visualization saved to: {output_path}"))

        except Exception as e:
            raise CommandError(f"Error visualizing graph: {e}") from e

    def list_available_graphs(self):
        """List all available graphs."""
        self.stdout.write("Available graphs:")
        self.stdout.write("-" * 50)

        for app_name, graph_name, version in _GRAPH_REGISTRY.keys():
            is_latest = _LATEST_VERSIONS.get((app_name, graph_name)) == version
            status = " (latest)" if is_latest else ""
            self.stdout.write(f"  {app_name}:{graph_name}:{version}{status}")

    def create_visualization(self, graph, graph_name, version, output_dir, format="png"):
        """Create the graph visualization using LangGraph's built-in methods."""
        filename = f"{graph_name}_{version or 'latest'}.{format}"
        output_path = os.path.join(output_dir, filename)

        if format == "ascii":
            # Use LangGraph's ASCII visualization
            try:
                ascii_output = graph.get_graph().draw_ascii()
                with open(output_path, "w") as f:
                    f.write(ascii_output)
                self.stdout.write("ASCII visualization:")
                self.stdout.write(ascii_output)
            except Exception as e:
                # Fallback to simple text if ASCII fails
                self.stdout.write(
                    self.style.WARNING(f"ASCII generation failed: {e}. Using simple text.")
                )
                self.create_simple_text_visualization(graph, graph_name, version, output_path)
        else:
            # Use LangGraph's Mermaid PNG visualization
            try:
                png_data = graph.get_graph().draw_mermaid_png()
                with open(output_path, "wb") as f:
                    f.write(png_data)
            except Exception as e:
                # If PNG generation fails, raise an error
                raise CommandError(
                    f"PNG generation failed: {e}. This graph has cache key issues "
                    f"that prevent LangGraph visualization. "
                    f"Try using --format ascii for text output."
                ) from e

        return output_path

    def create_simple_text_visualization(self, graph, graph_name, version, output_path):
        """Create a simple text representation when LangGraph visualization fails."""
        try:
            # Get basic graph structure from the builder
            builder = graph.builder
            nodes = list(builder.nodes.keys())
            edges = list(builder.edges)

            # Create simple text representation
            text_output = f"Graph: {graph_name} (v{version or 'latest'})\n"
            text_output += "=" * 50 + "\n\n"
            text_output += f"Nodes ({len(nodes)}):\n"
            for node in sorted(nodes):
                text_output += f"  - {node}\n"

            text_output += f"\nEdges ({len(edges)}):\n"
            for edge in sorted(edges):
                text_output += f"  {edge[0]} -> {edge[1]}\n"

            # Write to file
            with open(output_path, "w") as f:
                f.write(text_output)

            self.stdout.write("Simple text visualization:")
            self.stdout.write(text_output)

        except Exception as e:
            # Final fallback - just create a basic info file
            basic_info = f"Graph: {graph_name} (v{version or 'latest'})\n"
            basic_info += f"Error: Could not generate visualization - {e}\n"
            with open(output_path, "w") as f:
                f.write(basic_info)
            self.stdout.write(f"Created basic info file due to error: {e}")
