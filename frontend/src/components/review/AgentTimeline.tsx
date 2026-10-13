import { AGENT_DISPLAY_ORDER } from "@/config/constants";
import { AgentNode } from "@/components/review/AgentNode";
import type { AgentProgress } from "@/types";

const groupOne = new Set(
  AGENT_DISPLAY_ORDER.filter((agent) => agent.parallelGroup === 1).map(
    (agent) => agent.name,
  ),
);

const groupTwo = new Set(
  AGENT_DISPLAY_ORDER.filter((agent) => agent.parallelGroup === 2).map(
    (agent) => agent.name,
  ),
);

export function AgentTimeline({ agents }: { agents: AgentProgress[] }) {
  const nodes: Array<{ type: "single" | "parallel"; items: AgentProgress[] }> =
    [];

  for (const agent of agents) {
    if (groupOne.has(agent.name) || groupTwo.has(agent.name)) {
      continue;
    }

    nodes.push({ type: "single", items: [agent] });

    if (agent.name === "supervisor") {
      nodes.push({
        type: "parallel",
        items: agents.filter((entry) => groupOne.has(entry.name)),
      });
    }

    if (agent.name === "report_writer") {
      nodes.push({
        type: "parallel",
        items: agents.filter((entry) => groupTwo.has(entry.name)),
      });
    }
  }

  return (
    <div className="space-y-2">
      {nodes.map((node, index) =>
        node.type === "single" ? (
          <AgentNode key={node.items[0].name} agent={node.items[0]} />
        ) : (
          <div
            key={`parallel-${index}`}
            className="flex flex-col gap-2 md:flex-row"
          >
            {node.items.map((agent) => (
              <AgentNode key={agent.name} agent={agent} stretch />
            ))}
          </div>
        ),
      )}
    </div>
  );
}
