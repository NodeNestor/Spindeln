import { useEffect, useState, useRef, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import ForceGraph2D, {
  ForceGraphMethods,
  NodeObject,
  LinkObject,
} from "react-force-graph-2d";
import {
  Loader2,
  AlertTriangle,
  ArrowLeft,
  ZoomIn,
  ZoomOut,
  Maximize2,
} from "lucide-react";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8082";

interface GraphNode {
  id: string;
  name: string;
  type: "person" | "company" | "address" | "phone" | "email";
  val?: number;
}

interface GraphLink {
  source: string;
  target: string;
  label?: string;
}

const typeColors: Record<string, string> = {
  person: "#0ea5e9",
  company: "#10b981",
  address: "#f59e0b",
  phone: "#8b5cf6",
  email: "#ec4899",
};

export default function Graph() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const fgRef = useRef<ForceGraphMethods>();
  const containerRef = useRef<HTMLDivElement>(null);

  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [links, setLinks] = useState<GraphLink[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 });
  const [hoveredNode, setHoveredNode] = useState<GraphNode | null>(null);

  // Resize handler
  useEffect(() => {
    const updateDimensions = () => {
      if (containerRef.current) {
        setDimensions({
          width: containerRef.current.clientWidth,
          height: containerRef.current.clientHeight,
        });
      }
    };

    updateDimensions();
    window.addEventListener("resize", updateDimensions);
    return () => window.removeEventListener("resize", updateDimensions);
  }, []);

  // Fetch graph data
  useEffect(() => {
    const fetchGraph = async () => {
      try {
        const res = await fetch(`${API_URL}/api/persons/${id}/graph`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);

        const data = await res.json();
        setNodes(data.nodes || []);
        setLinks(data.links || data.edges || []);
      } catch (err: any) {
        setError(err.message || "Failed to load graph");
      } finally {
        setLoading(false);
      }
    };

    if (id) fetchGraph();
  }, [id]);

  // Configure forces
  useEffect(() => {
    if (fgRef.current && nodes.length > 0) {
      fgRef.current.d3Force("charge")?.strength(-200);
      fgRef.current.d3Force("link")?.distance(100);
    }
  }, [nodes]);

  const handleNodeClick = useCallback(
    (node: NodeObject) => {
      const gNode = node as unknown as GraphNode;
      if (gNode.type === "person") {
        navigate(`/profile/${gNode.id}`);
      }
    },
    [navigate]
  );

  const paintNode = useCallback(
    (node: NodeObject, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const gNode = node as unknown as GraphNode;
      const x = node.x || 0;
      const y = node.y || 0;
      const color = typeColors[gNode.type] || "#71717a";
      const isHovered = hoveredNode?.id === gNode.id;
      const radius = gNode.type === "person" ? 8 : 5;
      const renderRadius = isHovered ? radius * 1.4 : radius;

      // Glow
      ctx.shadowColor = color;
      ctx.shadowBlur = isHovered ? 16 : 10;

      // Circle
      ctx.beginPath();
      ctx.arc(x, y, renderRadius, 0, 2 * Math.PI);
      ctx.fillStyle = color;
      ctx.fill();

      ctx.shadowBlur = 0;

      // Border ring for hovered
      if (isHovered) {
        ctx.beginPath();
        ctx.arc(x, y, renderRadius + 3, 0, 2 * Math.PI);
        ctx.strokeStyle = color;
        ctx.lineWidth = 1;
        ctx.setLineDash([3, 3]);
        ctx.stroke();
        ctx.setLineDash([]);
      }

      // Label
      const fontSize = Math.max(12 / globalScale, 3);
      ctx.font = `${fontSize}px sans-serif`;
      ctx.textAlign = "center";
      ctx.textBaseline = "top";
      ctx.fillStyle = "#d4d4d8";
      ctx.fillText(gNode.name || "", x, y + renderRadius + 3);

      // Type label (smaller)
      if (globalScale > 1.5) {
        ctx.font = `${fontSize * 0.7}px sans-serif`;
        ctx.fillStyle = "#71717a";
        ctx.fillText(gNode.type, x, y + renderRadius + 3 + fontSize + 1);
      }
    },
    [hoveredNode]
  );

  const paintLink = useCallback(
    (link: LinkObject, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const start = link.source as NodeObject;
      const end = link.target as NodeObject;
      if (!start?.x || !end?.x) return;

      ctx.beginPath();
      ctx.moveTo(start.x, start.y || 0);
      ctx.lineTo(end.x, end.y || 0);
      ctx.strokeStyle = "#3f3f4680";
      ctx.lineWidth = 1;
      ctx.stroke();

      // Link label
      const gLink = link as unknown as GraphLink;
      if (gLink.label && globalScale > 2) {
        const midX = ((start.x || 0) + (end.x || 0)) / 2;
        const midY = ((start.y || 0) + (end.y || 0)) / 2;
        const fontSize = Math.max(8 / globalScale, 2);
        ctx.font = `${fontSize}px sans-serif`;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillStyle = "#52525b";
        ctx.fillText(gLink.label, midX, midY);
      }
    },
    []
  );

  const zoomIn = () => fgRef.current?.zoom(2, 400);
  const zoomOut = () => fgRef.current?.zoom(0.5, 400);
  const fitAll = () => fgRef.current?.zoomToFit(400, 60);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[80vh]">
        <Loader2 className="w-8 h-8 animate-spin text-sky-400" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-[80vh] text-zinc-400">
        <AlertTriangle className="w-10 h-10 text-red-400 mb-3" />
        <p className="text-sm">{error}</p>
        <button
          onClick={() => navigate(-1)}
          className="btn-secondary mt-4 text-sm"
        >
          Go back
        </button>
      </div>
    );
  }

  const graphData = {
    nodes: nodes.map((n) => ({
      ...n,
      val: n.val || (n.type === "person" ? 8 : 5),
    })),
    links: links.map((l) => ({ ...l })),
  };

  return (
    <div className="space-y-3 -m-6">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-6 pt-6">
        <button
          onClick={() => navigate(-1)}
          className="flex items-center gap-2 text-sm text-zinc-400 hover:text-zinc-200 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Back
        </button>

        <div className="flex items-center gap-2">
          {/* Legend */}
          <div className="flex items-center gap-3 mr-4">
            {Object.entries(typeColors).map(([type, color]) => (
              <div key={type} className="flex items-center gap-1.5">
                <div
                  className="w-2.5 h-2.5 rounded-full"
                  style={{ backgroundColor: color }}
                />
                <span className="text-xs text-zinc-500 capitalize">
                  {type}
                </span>
              </div>
            ))}
          </div>

          <button onClick={zoomIn} className="btn-secondary p-2">
            <ZoomIn className="w-4 h-4" />
          </button>
          <button onClick={zoomOut} className="btn-secondary p-2">
            <ZoomOut className="w-4 h-4" />
          </button>
          <button onClick={fitAll} className="btn-secondary p-2">
            <Maximize2 className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Graph */}
      <div
        ref={containerRef}
        className="w-full bg-zinc-950"
        style={{ height: "calc(100vh - 100px)" }}
      >
        <ForceGraph2D
          ref={fgRef}
          graphData={graphData}
          width={dimensions.width}
          height={dimensions.height}
          backgroundColor="#09090b"
          nodeCanvasObject={paintNode}
          linkCanvasObject={paintLink}
          onNodeClick={handleNodeClick}
          onNodeHover={(node) =>
            setHoveredNode(node ? (node as unknown as GraphNode) : null)
          }
          cooldownTicks={200}
          enableNodeDrag={true}
          enableZoomInteraction={true}
        />
      </div>

      {/* Hovered node info */}
      {hoveredNode && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 bg-zinc-900 border border-zinc-700 rounded-lg px-4 py-2 shadow-xl z-50 animate-fade-in">
          <div className="flex items-center gap-2">
            <div
              className="w-3 h-3 rounded-full"
              style={{
                backgroundColor: typeColors[hoveredNode.type] || "#71717a",
              }}
            />
            <span className="text-sm font-medium text-zinc-200">
              {hoveredNode.name}
            </span>
            <span className="text-xs text-zinc-500 capitalize">
              ({hoveredNode.type})
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
