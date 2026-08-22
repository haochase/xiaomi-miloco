import { useTranslation } from "react-i18next";
import type { AgentRegistry } from "@/agents/registry";
import { serializeAppRoute } from "@/lib/appRoute";

interface Props {
  registry: AgentRegistry;
  successfulCapabilityIds: ReadonlySet<string>;
  agentId?: string;
}

export function AgentsPage({
  registry,
  successfulCapabilityIds,
  agentId,
}: Props) {
  const { t } = useTranslation();
  const visible = registry.visibleFor(successfulCapabilityIds);

  if (agentId !== undefined) {
    const contribution = registry.find(agentId);
    const isVisible =
      contribution !== undefined &&
      successfulCapabilityIds.has(contribution.capabilityId);

    if (!isVisible) {
      return (
        <section className="max-w-[720px] py-4 md:py-8">
          <h1 className="text-title text-text-primary">
            {t("agents.notFoundTitle")}
          </h1>
          <p className="mt-2 text-body text-text-secondary">
            {t("agents.notFound")}
          </p>
          <a
            href={serializeAppRoute({ kind: "agents" })}
            className="inline-flex mt-5 text-body text-brand-primary hover:text-brand-primary/80"
          >
            {t("agents.back")}
          </a>
        </section>
      );
    }

    return <>{contribution.render()}</>;
  }

  if (visible.length === 0) {
    return (
      <section className="max-w-[720px] py-4 md:py-8">
        <h1 className="text-title text-text-primary">{t("agents.title")}</h1>
        <p className="mt-2 text-body text-text-secondary">{t("agents.empty")}</p>
      </section>
    );
  }

  return (
    <section className="max-w-[960px] py-4 md:py-8">
      <h1 className="text-title text-text-primary">{t("agents.title")}</h1>
      <div className="mt-5 grid gap-3 sm:grid-cols-2">
        {visible.map((contribution) => {
          const Icon = contribution.Icon;
          return (
            <a
              key={contribution.id}
              href={serializeAppRoute({
                kind: "agents",
                agentId: contribution.id,
              })}
              className="flex min-h-16 items-center gap-3 rounded-md border border-border px-4 py-3 text-text-primary hover:border-border-strong hover:bg-bg-secondary transition-colors"
            >
              <Icon className="shrink-0 text-brand-primary" width={24} height={24} />
              <span className="text-body">{t(contribution.labelKey)}</span>
            </a>
          );
        })}
      </div>
    </section>
  );
}
