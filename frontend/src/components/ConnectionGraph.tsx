import { useCallback, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import ForceGraph2D, {
  ForceGraphMethods,
  NodeObject,
  LinkObject,
} from "react-force-graph-2d";

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

interface ConnectionGraphProps {
  nodes: GraphNode[];
  links: GraphLink[];
  width?: number;
  height?: number;
  className?: string;
  onNodeClick?: (node: GraphNode) => void;
}

const typeColors: Record<string, string> = {
  person: "#0ea5e9",    // sky-500
  company: "#10b981",   // emerald-500
  address: "#f59e0b",   // amber-500
  phone: "#8b5cf6",     // violet-500
  email: "#ec4899",     // pink-500
};

export default function ConnectionGraph({
  nodes,
  links,
  width,
  height = 400,
  className = "",
  onNodeClick,
}: ConnectionGraphProps) {
  const navigate = useNavigate();
  const fgRef = useRef<ForceGraphMethods>();

  const graphData = {
    nodes: nodes.map((n) => ({ ...n, val: n.val || (n.type === "person" ? 8 : 5) })),
    links: links.map((l) => ({ ...l })),
  };

  useEffect(() => {
    if (fgRef.current) {
      fgRef.current.d3Force("charge")?.strength(-120);
      fgRef.current.d3Force("link")?.distance(80);
    }
  }, []);

  const handleNodeClick = useCallback(
    (node: NodeObject) => {
      const gNode = node as unknown as GraphNode;
      if (onNodeClick) {
        onNodeClick(gNode);
      } else if (gNode.type === "person") {
        navigate(`/profile/${gNode.id}`);
      }
    },
    [navigate, onNodeClick]
  );

  const paintNode = useCallback(
    (node: NodeObject, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const gNode = node as unknown as GraphNode;
      const x = node.x || 0;
      const y = node.y || 0;
      const color = typeColors[gNode.type] || "#71717a";
      const radius = gNode.type === "person" ? 6 : 4;

      // Glow effect
      ctx.shadowColor = color;
      ctx.shadowBlur = 8;

      // Node circle
      ctx.beginPath();
      ctx.arc(x, y, radius, 0, 2 * Math.PI);
      ctx.fillStyle = color;
      ctx.fill();

      // Border
      ctx.shadowBlur = 0;
      ctx.strokeStyle = color;
      ctx.lineWidth = 0.5;
      ctx.stroke();

      // Label
      const fontSize = Math.max(10 / globalScale, 3);
      ctx.font = `${fontSize}px sans-serif`;
      ctx.textAlign = "center";
      ctx.textBaseline = "top";
      ctx.fillStyle = "#d4d4d8";
      ctx.shadowBlur = 0;
      ctx.fillText(gNode.name || "", x, y + radius + 2);
    },
    []
  );

  const paintLink = useCallback(
    (link: LinkObject, ctx: CanvasRenderingContext2D) => {
      const start = link.source as NodeObject;
      const end = link.target as NodeObject;
      if (!start?.x || !end?.x) return;

      ctx.beginPath();
      ctx.moveTo(start.x, start.y || 0);
      ctx.lineTo(end.x, end.y || 0);
      ctx.strokeStyle = "#3f3f46";
      ctx.lineWidth = 0.8;
      ctx.stroke();
    },
    []
  );

  return (
    <div className={`rounded-lg overflow-hidden bg-zinc-950 ${className}`}>
      <ForceGraph2D
        ref={fgRef}
        graphData={graphData}
        width={width}
        height={height}
        backgroundColor="#09090b"
        nodeCanvasObject={paintNode}
        linkCanvasObject={paintLink}
        onNodeClick={handleNodeClick}
        cooldownTicks={100}
        enableNodeDrag={true}
        enableZoomInteraction={true}
      />
    </div>
  );
}
