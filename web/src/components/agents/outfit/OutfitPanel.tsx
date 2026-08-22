import { useState } from "react";
import { useTranslation } from "react-i18next";
import { getOutfitCapability, getOutfitUsageToday } from "@/api";
import type { OutfitCapability, OutfitUsageToday } from "@/api";
import { Segmented } from "@/components/Segmented";
import { useAsync } from "@/hooks/useAsync";
import { OutfitTryOnReview } from "./OutfitTryOnReview";

export type OutfitPanelView = "today" | "wardrobe" | "tryOn";

export interface OutfitPanelLoadState<T> {
  data: T | undefined;
  loading: boolean;
  error: Error | undefined;
}

export type OutfitPanelPhase =
  | { kind: "loading" }
  | { kind: "error"; retryTarget: "capability" | "usage" }
  | { kind: "ready"; capability: OutfitCapability; usage: OutfitUsageToday };

export function resolveOutfitPanelPhase({
  capability,
  usage,
}: {
  capability: OutfitPanelLoadState<OutfitCapability>;
  usage: OutfitPanelLoadState<OutfitUsageToday>;
}): OutfitPanelPhase {
  if (capability.error) {
    return { kind: "error", retryTarget: "capability" };
  }
  if (usage.error) {
    return { kind: "error", retryTarget: "usage" };
  }
  if (capability.loading || usage.loading) {
    return { kind: "loading" };
  }
  if (!capability.data || !usage.data) {
    return { kind: "loading" };
  }
  return { kind: "ready", capability: capability.data, usage: usage.data };
}

interface ReadyContentProps {
  capability: OutfitCapability;
  usage: OutfitUsageToday;
  activeView: OutfitPanelView;
  onViewChange: (view: OutfitPanelView) => void;
}

function CapabilityFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-border py-2 last:border-b-0">
      <dt className="text-caption text-text-secondary">{label}</dt>
      <dd className="text-body text-text-primary">{value}</dd>
    </div>
  );
}

function UsageValue({ value }: { value: number | null }) {
  const { t } = useTranslation();
  return <dd className="text-body text-text-primary">{value ?? t("agents.outfit.admin.unknown")}</dd>;
}

function AdminUsageDiagnostics({ usage }: { usage: OutfitUsageToday }) {
  const { t } = useTranslation();
  return (
    <section className="border-t border-border pt-5" aria-label={t("agents.outfit.admin.title")}>
      <h2 className="text-title text-text-primary">{t("agents.outfit.admin.title")}</h2>
      <dl className="mt-3 divide-y divide-border">
        <div className="flex items-baseline justify-between gap-4 py-2">
          <dt className="text-caption text-text-secondary">{t("agents.outfit.admin.date")}</dt>
          <dd className="text-body text-text-primary">{usage.date}</dd>
        </div>
        <div className="flex items-baseline justify-between gap-4 py-2">
          <dt className="text-caption text-text-secondary">{t("agents.outfit.admin.timezone")}</dt>
          <dd className="text-body text-text-primary">{usage.timezone}</dd>
        </div>
        <div className="flex items-baseline justify-between gap-4 py-2">
          <dt className="text-caption text-text-secondary">{t("agents.outfit.admin.callCount")}</dt>
          <dd className="text-body text-text-primary">{usage.callCount}</dd>
        </div>
        <div className="flex items-baseline justify-between gap-4 py-2">
          <dt className="text-caption text-text-secondary">{t("agents.outfit.admin.inputTokens")}</dt>
          <UsageValue value={usage.inputTokens} />
        </div>
        <div className="flex items-baseline justify-between gap-4 py-2">
          <dt className="text-caption text-text-secondary">{t("agents.outfit.admin.outputTokens")}</dt>
          <UsageValue value={usage.outputTokens} />
        </div>
        <div className="flex items-baseline justify-between gap-4 py-2">
          <dt className="text-caption text-text-secondary">{t("agents.outfit.admin.estimatedTotalTokens")}</dt>
          <UsageValue value={usage.estimatedTotalTokens} />
        </div>
        <div className="flex items-baseline justify-between gap-4 py-2">
          <dt className="text-caption text-text-secondary">{t("agents.outfit.admin.complete")}</dt>
          <dd className="text-body text-text-primary">
            {t(usage.complete ? "agents.outfit.status.yes" : "agents.outfit.status.no")}
          </dd>
        </div>
      </dl>
    </section>
  );
}

export function OutfitPanelReadyContent({
  capability,
  usage,
  activeView,
  onViewChange,
}: ReadyContentProps) {
  const { t } = useTranslation();
  const facts = [
    ["enabled", capability.enabled],
    ["primaryPersonConfigured", capability.primaryPersonConfigured],
    ["storageReady", capability.storageReady],
    ["voiceIngressConfigured", capability.voiceIngressConfigured],
    ["cameraAllowlisted", capability.cameraAllowlisted],
  ] as const;

  return (
    <section className="max-w-[960px] space-y-6 py-4 md:py-8" aria-label={t("agents.outfit.title")}>
      <Segmented<OutfitPanelView>
        ariaLabel={t("agents.outfit.viewLabel")}
        value={activeView}
        onChange={onViewChange}
        options={[
          { key: "today", label: t("agents.outfit.views.today") },
          { key: "wardrobe", label: t("agents.outfit.views.wardrobe") },
          { key: "tryOn", label: t("agents.outfit.views.tryOn") },
        ]}
      />
      {activeView === "today" && (
        <section aria-label={t("agents.outfit.today.title")}>
          <h1 className="text-title text-text-primary">{t("agents.outfit.today.title")}</h1>
          <p className="mt-2 text-body text-text-secondary">{t("agents.outfit.today.empty")}</p>
          <dl className="mt-4 divide-y divide-border">
            {facts.map(([key, value]) => (
              <CapabilityFact
                key={key}
                label={t(`agents.outfit.facts.${key}`)}
                value={t(value ? "agents.outfit.status.yes" : "agents.outfit.status.no")}
              />
            ))}
            <CapabilityFact
              label={t("agents.outfit.facts.providerStatus")}
              value={t(`agents.outfit.provider.${capability.lastProviderStatus}`)}
            />
          </dl>
        </section>
      )}
      {activeView === "wardrobe" && (
        <section aria-label={t("agents.outfit.wardrobe.title")}>
          <h1 className="text-title text-text-primary">{t("agents.outfit.wardrobe.title")}</h1>
          <p className="mt-2 text-body text-text-secondary">
            {t("agents.outfit.wardrobe.storage", {
              status: t(
                capability.storageReady
                  ? "agents.outfit.status.yes"
                  : "agents.outfit.status.no",
              ),
            })}
          </p>
          <p className="mt-4 text-body text-text-secondary">{t("agents.outfit.wardrobe.empty")}</p>
        </section>
      )}
      {activeView === "tryOn" && (
        <section aria-label={t("agents.outfit.review.title")}>
          <h1 className="text-title text-text-primary">{t("agents.outfit.review.title")}</h1>
          <div className="mt-4">
            <OutfitTryOnReview />
          </div>
        </section>
      )}
      <AdminUsageDiagnostics usage={usage} />
    </section>
  );
}

function OutfitPanelReady({ capability, usage }: Pick<ReadyContentProps, "capability" | "usage">) {
  const [activeView, setActiveView] = useState<OutfitPanelView>("today");
  return (
    <OutfitPanelReadyContent
      capability={capability}
      usage={usage}
      activeView={activeView}
      onViewChange={setActiveView}
    />
  );
}

export function OutfitPanel() {
  const { t } = useTranslation();
  const capability = useAsync(() => getOutfitCapability(), [], {
    errorLabel: t("agents.outfit.loadCapabilityFailed"),
  });
  const usage = useAsync(() => getOutfitUsageToday(), [], {
    errorLabel: t("agents.outfit.loadUsageFailed"),
  });
  const phase = resolveOutfitPanelPhase({ capability, usage });

  if (phase.kind === "loading") {
    return (
      <section className="max-w-[960px] py-4 md:py-8" role="status">
        <p className="text-body text-text-secondary">{t("agents.outfit.loading")}</p>
      </section>
    );
  }

  if (phase.kind === "error") {
    const retry = phase.retryTarget === "capability" ? capability.reload : usage.reload;
    return (
      <section className="max-w-[960px] py-4 md:py-8" role="alert">
        <p className="text-body text-text-secondary">{t("agents.outfit.loadFailed")}</p>
        <button
          type="button"
          onClick={() => void retry()}
          className="mt-4 min-h-9 rounded-md border border-border px-3 py-2 text-body text-text-primary transition-colors hover:border-border-strong"
        >
          {t("agents.outfit.retry")}
        </button>
      </section>
    );
  }

  return <OutfitPanelReady capability={phase.capability} usage={phase.usage} />;
}
