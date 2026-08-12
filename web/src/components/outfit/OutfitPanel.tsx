import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { AgentPanelContribution, AgentPanelIcon } from "@/agents/types";
import { IconAgents } from "@/lib/navIcons";
import { OutfitMomentsView } from "./OutfitMomentsView";
import { OutfitTodayView } from "./OutfitTodayView";
import { OutfitWardrobeView } from "./OutfitWardrobeView";
import {
  initialOutfitPanelSection,
  type OutfitPanelSection,
} from "./outfitPanelSection";

export interface OutfitPanelProps {
  momentId?: string;
}

export function OutfitPanel({ momentId }: OutfitPanelProps) {
  const { t } = useTranslation();
  const [section, setSection] = useState<OutfitPanelSection>(() =>
    initialOutfitPanelSection(momentId),
  );

  return (
    <section className="space-y-5" aria-labelledby="outfit-panel-title">
      <header className="space-y-1">
        <h1 id="outfit-panel-title" className="text-title text-text-primary">
          {t("outfit.title")}
        </h1>
        <p className="text-body text-text-secondary">{t("outfit.hint")}</p>
      </header>
      <div
        className="inline-flex max-w-full overflow-x-auto border border-border bg-bg-secondary"
        aria-label={t("outfit.sectionsAria")}
      >
        {(["today", "wardrobe", "moments"] as const).map((item) => {
          const active = section === item;
          return (
            <button
              key={item}
              type="button"
              aria-pressed={active}
              onClick={() => setSection(item)}
              className={`shrink-0 px-3 py-2 text-body transition-colors ${
                active
                  ? "bg-brand-soft text-text-primary"
                  : "text-text-secondary hover:bg-bg-tertiary"
              }`}
            >
              {t(`outfit.sections.${item}`)}
            </button>
          );
        })}
      </div>
      {section === "moments" ? (
        <OutfitMomentsView momentId={momentId} />
      ) : section === "wardrobe" ? (
        <OutfitWardrobeView />
      ) : (
        <OutfitTodayView />
      )}
    </section>
  );
}

export function createOutfitPanelContribution(
): AgentPanelContribution {
  return {
    id: "outfit",
    labelKey: "outfit.title",
    hintKey: "outfit.hint",
    capabilityId: "outfit_v2",
    Icon: IconAgents as AgentPanelIcon,
    render: ({ momentId }) => <OutfitPanel momentId={momentId} />,
  };
}
