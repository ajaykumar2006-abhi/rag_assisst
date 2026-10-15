import { Fragment } from "react";

import type { Stage } from "@/types/api";
import { formatMilliseconds } from "@/services/format";
import { Pill } from "./Pill";

const STATE_MARKER: Record<Stage["state"], string> = {
  pending: "·",
  running: "●",
  completed: "✓",
  failed: "✕",
};

function durationLabel(stage: Stage): string | null {
  if (!stage.started_at || !stage.finished_at) return null;
  const start = new Date(stage.started_at).getTime();
  const end = new Date(stage.finished_at).getTime();
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return null;
  return formatMilliseconds(end - start);
}

/**
 * Renders the seven real pipeline stages reported by the backend.
 *
 * Every value shown (state, detail text, timing) comes from the API response, so
 * this is a true progress view rather than a decorative animation.
 */
export function StageTimeline({ stages }: { stages: Stage[] }) {
  if (stages.length === 0) {
    return <p className="text-muted">No pipeline stages reported yet.</p>;
  }

  return (
    <ol className="stages">
      {stages.map((stage, index) => {
        const duration = durationLabel(stage);
        return (
          <Fragment key={stage.name}>
            <li className={`stage stage--${stage.state}`}>
              <span className="stage__marker" aria-hidden="true">
                {STATE_MARKER[stage.state]}
              </span>
              <div>
                <p className="stage__label">
                  <span>
                    {index + 1}. {stage.label}
                  </span>
                  <Pill tone={stage.state}>{stage.state}</Pill>
                  {duration ? <span className="stage__timing">{duration}</span> : null}
                </p>
                {stage.detail ? <p className="stage__detail">{stage.detail}</p> : null}
              </div>
            </li>
          </Fragment>
        );
      })}
    </ol>
  );
}
