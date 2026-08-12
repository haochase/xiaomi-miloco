import { useTranslation } from "react-i18next";
import { getOutfitMoment } from "@/api";
import { formatAgentMomentsRoute } from "@/lib/appRoute";
import { useAsync } from "@/hooks/useAsync";
import { OutfitMediaActions } from "./OutfitMediaActions";
import { OutfitTagReview } from "./OutfitTagReview";

interface Props {
  momentId: string;
}

export function OutfitMomentDetail({ momentId }: Props) {
  const { t } = useTranslation();
  const moment = useAsync(
    () => getOutfitMoment(momentId),
    [momentId],
    { errorLabel: t("outfit.loadError") },
  );

  const close = () => {
    window.location.hash = formatAgentMomentsRoute("outfit");
  };

  if (moment.loading && !moment.data) {
    return <p className="py-8 text-center text-body text-text-secondary">{t("outfit.detail.loading")}</p>;
  }
  if (moment.error) {
    return (
      <section className="space-y-3 py-8 text-center" role="alert">
        <p className="text-body text-error">{t("outfit.detail.notFound")}</p>
        <button
          type="button"
          onClick={close}
          className="border border-border px-3 py-2 text-caption text-text-secondary hover:bg-bg-secondary"
        >
          {t("outfit.detail.back")}
        </button>
      </section>
    );
  }
  if (!moment.data) {
    return null;
  }

  return (
    <article className="space-y-5">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-section-title text-text-primary">{t("outfit.detail.title")}</h2>
        <button
          type="button"
          onClick={close}
          className="shrink-0 border border-border px-3 py-2 text-caption text-text-secondary hover:bg-bg-secondary"
        >
          {t("outfit.detail.back")}
        </button>
      </div>
      <dl className="grid gap-px border border-border bg-border sm:grid-cols-2">
        <Fact label={t("outfit.detail.items")} value={moment.data.itemIds.join(" · ")} />
        <Fact label={t("outfit.detail.recommendation")} value={moment.data.recommendationId} />
        <Fact label={t("outfit.detail.source")} value={moment.data.confirmedWearEventId} />
        <Fact label={t("outfit.detail.timezone")} value={moment.data.timezone} />
      </dl>
      {moment.data.mediaAssetIds.length ? (
        <section className="border-t border-border pt-4">
          <h3 className="text-title text-text-primary">{t("outfit.media.title")}</h3>
          <div className="mt-3 space-y-5">
            {moment.data.mediaAssetIds.map((assetId) => (
              <OutfitMediaActions
                key={assetId}
                assetId={assetId}
                onDeleted={moment.reload}
              />
            ))}
          </div>
        </section>
      ) : null}
      {moment.data.userNote ? (
        <section className="border-t border-border pt-4">
          <h3 className="text-title text-text-primary">{t("outfit.detail.note")}</h3>
          <p className="mt-2 break-words text-body text-text-secondary">{moment.data.userNote}</p>
        </section>
      ) : null}
      <section className="border-t border-border pt-4">
        <h3 className="text-title text-text-primary">{t("outfit.detail.confirmedTags")}</h3>
        {moment.data.confirmedTags.length ? (
          <ul className="mt-2 space-y-2">
            {moment.data.confirmedTags.map((tag) => (
              <li key={tag.id} className="break-words text-body text-text-secondary">
                <span className="text-text-primary">{tag.label}</span>
                {": "}
                {tag.narrative}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-body text-text-secondary">{t("outfit.detail.noConfirmedTags")}</p>
        )}
      </section>
      <OutfitTagReview
        momentId={momentId}
        tags={moment.data.pendingTags}
        onChanged={moment.reload}
      />
    </article>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 bg-bg-primary px-4 py-3">
      <dt className="text-caption text-text-tertiary">{label}</dt>
      <dd className="mt-1 break-words text-body text-text-primary">{value}</dd>
    </div>
  );
}
