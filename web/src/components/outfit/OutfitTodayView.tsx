import { FormEvent, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  confirmOutfitRecommendedWear,
  listOutfitWardrobe,
  requestOutfitRecommendation,
} from "@/api";
import { toast } from "@/components/Toast";
import { useAsync } from "@/hooks/useAsync";
import { formatAgentMomentRoute } from "@/lib/appRoute";
import type { OutfitRecommendation } from "@/lib/types";
import { stableWearConfirmationId } from "./wearConfirmationId";

export function OutfitTodayView() {
  const { t } = useTranslation();
  const wardrobe = useAsync(listOutfitWardrobe, [], {
    errorLabel: t("outfit.today.loadError"),
  });
  const [occasion, setOccasion] = useState("");
  const [activity, setActivity] = useState("");
  const [recommendation, setRecommendation] = useState<OutfitRecommendation>();
  const [confirmedMomentId, setConfirmedMomentId] = useState<string>();
  const [confirmationIds, setConfirmationIds] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const namesById = useMemo(
    () => new Map((wardrobe.data ?? []).map((item) => [item.id, item.name])),
    [wardrobe.data],
  );

  const requestRecommendation = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setBusy(true);
    setConfirmedMomentId(undefined);
    setConfirmationIds({});
    void requestOutfitRecommendation({
      occasion: occasion.trim() || undefined,
      activity: activity.trim() || undefined,
    })
      .then((result) => {
        setRecommendation(result);
        if (result.status === "needs_context") {
          toast(t("outfit.today.contextRequired"), "warn");
        }
      })
      .catch((error) => {
        toast(
          error instanceof Error ? error.message : t("outfit.today.requestFailed"),
          "warn",
        );
      })
      .finally(() => setBusy(false));
  };

  const confirmWear = (optionId: string) => {
    if (!recommendation?.recommendationId) {
      return;
    }
    if (!window.confirm(t("outfit.today.confirmPrompt"))) {
      return;
    }
    const confirmationId = stableWearConfirmationId(
      recommendation.recommendationId,
      optionId,
      confirmationIds[optionId],
    );
    setConfirmationIds((current) => ({ ...current, [optionId]: confirmationId }));
    setBusy(true);
    void confirmOutfitRecommendedWear({
      recommendationId: recommendation.recommendationId,
      optionId,
      confirmationId,
    })
      .then((confirmation) => {
        setConfirmedMomentId(confirmation.momentId);
        toast(t("outfit.today.confirmed"), "ok");
      })
      .catch((error) => {
        toast(
          error instanceof Error ? error.message : t("outfit.today.confirmFailed"),
          "warn",
        );
      })
      .finally(() => setBusy(false));
  };

  return (
    <section className="space-y-6" aria-labelledby="outfit-today-title">
      <div className="space-y-1">
        <h2 id="outfit-today-title" className="text-section-title text-text-primary">
          {t("outfit.today.title")}
        </h2>
        <p className="text-body text-text-secondary">{t("outfit.today.hint")}</p>
      </div>

      <form
        className="grid gap-3 border border-border bg-bg-secondary p-4 sm:grid-cols-2"
        onSubmit={requestRecommendation}
      >
        <label className="grid gap-1 text-caption text-text-secondary">
          {t("outfit.today.occasion")}
          <input
            value={occasion}
            onChange={(event) => setOccasion(event.target.value)}
            className="min-h-10 border border-border bg-bg-primary px-3 text-body text-text-primary"
            maxLength={120}
          />
        </label>
        <label className="grid gap-1 text-caption text-text-secondary">
          {t("outfit.today.activity")}
          <input
            value={activity}
            onChange={(event) => setActivity(event.target.value)}
            className="min-h-10 border border-border bg-bg-primary px-3 text-body text-text-primary"
            maxLength={120}
          />
        </label>
        <div className="sm:col-span-2">
          <button
            type="submit"
            disabled={busy}
            className="min-h-10 border border-brand-primary bg-brand-primary px-4 text-body text-white disabled:opacity-60"
          >
            {busy ? t("outfit.today.working") : t("outfit.today.request")}
          </button>
        </div>
      </form>

      {wardrobe.error ? (
        <p className="text-body text-error">{t("outfit.today.loadError")}</p>
      ) : null}
      {recommendation ? (
        <RecommendationResult
          recommendation={recommendation}
          namesById={namesById}
          busy={busy}
          onConfirm={confirmWear}
        />
      ) : null}
      {confirmedMomentId ? (
        <button
          type="button"
          onClick={() => {
            window.location.hash = formatAgentMomentRoute("outfit", confirmedMomentId);
          }}
          className="min-h-10 border border-border px-4 text-body text-text-primary hover:bg-bg-secondary"
        >
          {t("outfit.today.viewMoment")}
        </button>
      ) : null}
    </section>
  );
}

interface RecommendationResultProps {
  recommendation: OutfitRecommendation;
  namesById: Map<string, string>;
  busy: boolean;
  onConfirm: (optionId: string) => void;
}

function RecommendationResult({
  recommendation,
  namesById,
  busy,
  onConfirm,
}: RecommendationResultProps) {
  const { t } = useTranslation();
  if (recommendation.status === "needs_context") {
    return <p className="text-body text-text-secondary">{t("outfit.today.contextRequired")}</p>;
  }
  if (!recommendation.options.length) {
    return (
      <p className="text-body text-text-secondary">
        {t("outfit.today.inventoryLimited", {
          hints: recommendation.inventoryHints
            .map((hint) => t(`outfit.today.hints.${hint}`))
            .join(" "),
        })}
      </p>
    );
  }
  return (
    <section className="space-y-3" aria-labelledby="outfit-recommendations-title">
      <div className="space-y-1">
        <h3 id="outfit-recommendations-title" className="text-title text-text-primary">
          {t("outfit.today.resultsTitle")}
        </h3>
        {recommendation.status === "insufficient_inventory" ? (
          <p className="text-caption text-text-secondary">
            {t("outfit.today.alternativeLimited")}
          </p>
        ) : null}
      </div>
      <ol className="grid gap-px border border-border bg-border sm:grid-cols-2">
        {recommendation.options.map((option, index) => (
          <li key={option.id} className="flex min-h-32 flex-col gap-3 bg-bg-primary p-4">
            <div className="min-w-0 grow">
              <p className="text-caption-mono text-text-tertiary">
                {t("outfit.today.option", { index: index + 1 })}
              </p>
              <p className="break-words text-body text-text-primary">
                {option.itemIds
                  .map((itemId) => namesById.get(itemId) ?? itemId)
                  .join(" / ")}
              </p>
            </div>
            <button
              type="button"
              disabled={busy}
              onClick={() => onConfirm(option.id)}
              className="min-h-10 border border-border px-3 text-caption text-text-primary disabled:opacity-60"
            >
              {t("outfit.today.confirmWear")}
            </button>
          </li>
        ))}
      </ol>
    </section>
  );
}
