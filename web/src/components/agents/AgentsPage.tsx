import { useTranslation } from "react-i18next";
import { getOutfitCapabilities } from "@/api";
import { listVisibleAgentPanelContributions } from "@/agents/capabilities";
import type { AgentPanelRegistry } from "@/agents/registry";
import { useAsync } from "@/hooks/useAsync";
import type { AppRoute } from "@/lib/appRoute";
import { formatAgentRoute } from "@/lib/appRoute";

interface Props {
  registry: AgentPanelRegistry;
  route: Extract<AppRoute, { tab: "agents" }>;
}

export function AgentsPage({ registry, route }: Props) {
  const { t } = useTranslation();
  const capabilities = useAsync(getOutfitCapabilities, [], {
    errorLabel: t("nav.agentsUnavailable"),
  });
  const contributions = capabilities.data
    ? listVisibleAgentPanelContributions(registry, capabilities.data)
    : [];
  const activeContribution = route.agentId
    ? contributions.find((contribution) => contribution.id === route.agentId)
    : undefined;

  if (capabilities.loading && !capabilities.data) {
    return <p className="text-body text-text-secondary">{t("common.loading")}</p>;
  }
  if (capabilities.error) {
    return <p className="text-body text-text-secondary">{t("nav.agentsUnavailable")}</p>;
  }
  if (route.agentId && !activeContribution) {
    return <p className="text-body text-text-secondary">{t("nav.agentsUnavailable")}</p>;
  }
  if (activeContribution) {
    return activeContribution.render({
      agentId: activeContribution.id,
      momentId: route.momentId,
    });
  }
  if (contributions.length === 0) {
    return <p className="text-body text-text-secondary">{t("nav.agentsEmpty")}</p>;
  }

  return (
    <section aria-labelledby="agents-page-title" className="space-y-4">
      <h1 id="agents-page-title" className="text-title text-text-primary">
        {t("nav.agents")}
      </h1>
      <div className="grid gap-2 sm:grid-cols-2">
        {contributions.map((contribution) => {
          const Icon = contribution.Icon;
          return (
            <button
              key={contribution.id}
              type="button"
              onClick={() => {
                window.location.hash = formatAgentRoute(contribution.id);
              }}
              className="flex min-h-20 items-center gap-3 border border-border px-4 py-3 text-left transition-colors hover:border-border-strong hover:bg-bg-secondary"
            >
              <span className="shrink-0 text-brand-primary">
                <Icon width={24} height={24} />
              </span>
              <span className="min-w-0">
                <span className="block text-title text-text-primary">
                  {t(contribution.labelKey)}
                </span>
                <span className="block text-caption text-text-tertiary">
                  {t(contribution.hintKey)}
                </span>
              </span>
            </button>
          );
        })}
      </div>
    </section>
  );
}
