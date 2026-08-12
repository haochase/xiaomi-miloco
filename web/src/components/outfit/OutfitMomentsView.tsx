import { useState } from "react";
import { useTranslation } from "react-i18next";
import { listOutfitMoments, type OutfitMomentQuery } from "@/api";
import { OutfitMomentDetail } from "./OutfitMomentDetail";
import { formatAgentMomentRoute } from "@/lib/appRoute";
import { useAsync } from "@/hooks/useAsync";
import type { OutfitMoment } from "@/lib/types";

export type MomentWindow = "recent10" | "recent30" | "month";

export function toMomentQuery(
  window: MomentWindow,
  nowMs: number,
): OutfitMomentQuery {
  if (window === "recent10") {
    return { limit: 10 };
  }
  if (window === "recent30") {
    return { limit: 30 };
  }
  const start = new Date(nowMs);
  start.setDate(start.getDate() - 30);
  return { limit: 30, sinceMs: start.getTime() };
}

interface Props {
  momentId?: string;
}

export function OutfitMomentsView({ momentId }: Props) {
  const { i18n, t } = useTranslation();
  const [window, setWindow] = useState<MomentWindow>("recent10");
  const moments = useAsync(
    () => listOutfitMoments(toMomentQuery(window, Date.now())),
    [window],
    { errorLabel: t("outfit.loadError") },
  );

  if (momentId) {
    return <OutfitMomentDetail momentId={momentId} />;
  }

  return (
    <section className="space-y-4" aria-labelledby="outfit-moments-title">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="outfit-moments-title" className="text-section-title text-text-primary">
          {t("outfit.moments.title")}
        </h2>
        <div className="flex max-w-full overflow-x-auto border border-border bg-bg-secondary">
          {(["recent10", "recent30", "month"] as const).map((item) => (
            <button
              key={item}
              type="button"
              aria-pressed={window === item}
              onClick={() => setWindow(item)}
              className={`shrink-0 px-3 py-2 text-caption transition-colors ${
                window === item
                  ? "bg-brand-soft text-text-primary"
                  : "text-text-secondary hover:bg-bg-tertiary"
              }`}
            >
              {t(`outfit.moments.filters.${item}`)}
            </button>
          ))}
        </div>
      </div>
      {moments.loading && !moments.data ? (
        <p className="py-8 text-center text-body text-text-secondary">
          {t("outfit.moments.loading")}
        </p>
      ) : moments.error ? (
        <div className="space-y-3 py-8 text-center" role="alert">
          <p className="text-body text-error">{t("outfit.moments.error")}</p>
          <button
            type="button"
            onClick={() => moments.reload()}
            className="border border-border px-3 py-2 text-caption text-text-secondary hover:bg-bg-secondary"
          >
            {t("common.retry")}
          </button>
        </div>
      ) : moments.data?.length ? (
        <ul className="grid gap-px border border-border bg-border sm:grid-cols-2">
          {moments.data.map((moment) => (
            <li key={moment.id} className="bg-bg-primary">
              <MomentListItem locale={i18n.language} moment={moment} />
            </li>
          ))}
        </ul>
      ) : (
        <p className="py-8 text-center text-body text-text-secondary">
          {t("outfit.moments.empty")}
        </p>
      )}
    </section>
  );
}

function MomentListItem({ locale, moment }: { locale: string; moment: OutfitMoment }) {
  const { t } = useTranslation();
  const labels = moment.confirmedTags.map((tag) => tag.label);
  const date = new Intl.DateTimeFormat(locale, {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(moment.occurredAt);

  return (
    <button
      type="button"
      onClick={() => {
        window.location.hash = formatAgentMomentRoute("outfit", moment.id);
      }}
      className="flex min-h-32 w-full flex-col items-start gap-2 px-4 py-4 text-left transition-colors hover:bg-bg-secondary"
    >
      <span className="text-caption-mono text-text-tertiary">{date}</span>
      <span className="break-words text-body text-text-primary">
        {moment.itemIds.join(" · ")}
      </span>
      {labels.length ? (
        <span className="break-words text-caption text-text-secondary">
          {labels.join(" · ")}
        </span>
      ) : (
        <span className="text-caption text-text-tertiary">
          {t("outfit.moments.noConfirmedTags")}
        </span>
      )}
    </button>
  );
}
