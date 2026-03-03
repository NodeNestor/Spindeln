import {
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
  ResponsiveContainer,
  Tooltip,
} from "recharts";

interface CategoryRadarProps {
  data: Record<string, number>;
  className?: string;
}

const categoryLabels: Record<string, string> = {
  personal: "Personal",
  financial: "Financial",
  companies: "Companies",
  social: "Social",
  breaches: "Breaches",
  contact: "Contact",
  address: "Address",
  news: "News",
};

export default function CategoryRadar({
  data,
  className = "",
}: CategoryRadarProps) {
  const chartData = Object.entries(data).map(([key, value]) => ({
    category: categoryLabels[key] || key,
    completeness: Math.round(value * 100),
    fullMark: 100,
  }));

  if (chartData.length === 0) {
    return (
      <div
        className={`flex items-center justify-center text-zinc-500 text-sm ${className}`}
      >
        No category data available
      </div>
    );
  }

  return (
    <div className={className}>
      <ResponsiveContainer width="100%" height={280}>
        <RadarChart data={chartData} cx="50%" cy="50%" outerRadius="70%">
          <PolarGrid stroke="#3f3f46" strokeDasharray="3 3" />
          <PolarAngleAxis
            dataKey="category"
            tick={{ fill: "#a1a1aa", fontSize: 11 }}
          />
          <PolarRadiusAxis
            angle={90}
            domain={[0, 100]}
            tick={{ fill: "#71717a", fontSize: 10 }}
            tickCount={5}
          />
          <Radar
            name="Completeness"
            dataKey="completeness"
            stroke="#0ea5e9"
            fill="#0ea5e9"
            fillOpacity={0.15}
            strokeWidth={2}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "#18181b",
              border: "1px solid #3f3f46",
              borderRadius: "8px",
              color: "#e4e4e7",
              fontSize: "12px",
            }}
            formatter={(value: number) => [`${value}%`, "Completeness"]}
          />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  );
}
