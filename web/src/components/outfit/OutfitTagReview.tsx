import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  confirmOutfitMomentTag,
  editOutfitMomentTag,
  refreshOutfitMomentTags,
  rejectOutfitMomentTag,
} from "@/api";
import { toast } from "@/components/Toast";
import type { OutfitMomentTag } from "@/lib/types";

interface Props {
  momentId: string;
  tags: OutfitMomentTag[];
  onChanged: () => Promise<void>;
}

type Action = "refresh" | "confirm" | "reject" | "edit";

export function OutfitTagReview({ momentId, tags, onChanged }: Props) {
  const { t } = useTranslation();
  const [busy, setBusy] = useState<Action | null>(null);
  const [editingTagId, setEditingTagId] = useState<string>();
  const [label, setLabel] = useState("");
  const [narrative, setNarrative] = useState("");

  const run = async (action: Action, operation: () => Promise<unknown>) => {
    setBusy(action);
    try {
      await operation();
      await onChanged();
    } catch (error) {
      toast(error instanceof Error ? error.message : t("outfit.tags.actionFailed"), "warn");
    } finally {
      setBusy(null);
    }
  };

  const beginEdit = (tag: OutfitMomentTag) => {
    setEditingTagId(tag.id);
    setLabel(tag.label);
    setNarrative(tag.narrative);
  };

  const submitEdit = (tag: OutfitMomentTag) => {
    const nextLabel = label.trim();
    const nextNarrative = narrative.trim();
    if (!nextLabel && !nextNarrative) {
      toast(t("outfit.tags.editRequired"), "warn");
      return;
    }
    void run("edit", async () => {
      await editOutfitMomentTag(momentId, tag.id, {
        ...(nextLabel ? { label: nextLabel } : {}),
        ...(nextNarrative ? { narrative: nextNarrative } : {}),
      });
      setEditingTagId(undefined);
    });
  };

  return (
    <section className="space-y-3 border-t border-border pt-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-title text-text-primary">{t("outfit.tags.title")}</h3>
          <p className="mt-1 text-caption text-text-secondary">{t("outfit.tags.hint")}</p>
        </div>
        <button
          type="button"
          disabled={busy !== null}
          onClick={() =>
            void run("refresh", () => refreshOutfitMomentTags(momentId))
          }
          className="border border-border px-3 py-2 text-caption text-text-secondary hover:bg-bg-secondary disabled:cursor-wait disabled:opacity-60"
        >
          {busy === "refresh" ? t("outfit.tags.working") : t("outfit.tags.refresh")}
        </button>
      </div>
      {tags.length ? (
        <ul className="space-y-3">
          {tags.map((tag) => {
            const editing = editingTagId === tag.id;
            return (
              <li key={tag.id} className="border border-border p-3">
                <p className="text-caption text-text-tertiary">{t("outfit.tags.systemSuggestion")}</p>
                {editing ? (
                  <div className="mt-3 space-y-2">
                    <label className="block text-caption text-text-secondary">
                      {t("outfit.tags.label")}
                      <input
                        value={label}
                        onChange={(event) => setLabel(event.target.value)}
                        className="mt-1 w-full border border-border bg-bg-primary px-3 py-2 text-body text-text-primary"
                      />
                    </label>
                    <label className="block text-caption text-text-secondary">
                      {t("outfit.tags.narrative")}
                      <textarea
                        value={narrative}
                        onChange={(event) => setNarrative(event.target.value)}
                        rows={3}
                        className="mt-1 w-full resize-y border border-border bg-bg-primary px-3 py-2 text-body text-text-primary"
                      />
                    </label>
                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        disabled={busy !== null}
                        onClick={() => submitEdit(tag)}
                        className="border border-border px-3 py-2 text-caption text-text-secondary hover:bg-bg-secondary disabled:cursor-wait disabled:opacity-60"
                      >
                        {busy === "edit" ? t("outfit.tags.working") : t("outfit.tags.save")}
                      </button>
                      <button
                        type="button"
                        disabled={busy !== null}
                        onClick={() => setEditingTagId(undefined)}
                        className="border border-border px-3 py-2 text-caption text-text-secondary hover:bg-bg-secondary disabled:cursor-wait disabled:opacity-60"
                      >
                        {t("outfit.tags.cancel")}
                      </button>
                    </div>
                  </div>
                ) : (
                  <>
                    <p className="mt-2 break-words text-body text-text-primary">{tag.label}</p>
                    <p className="mt-1 break-words text-body text-text-secondary">{tag.narrative}</p>
                    <p className="mt-2 text-caption text-text-tertiary">
                      {t("outfit.tags.evidenceCount", { count: tag.evidenceSignalIds.length })}
                    </p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      <button
                        type="button"
                        disabled={busy !== null}
                        onClick={() =>
                          void run("confirm", () =>
                            confirmOutfitMomentTag(momentId, tag.id),
                          )
                        }
                        className="border border-border px-3 py-2 text-caption text-text-secondary hover:bg-bg-secondary disabled:cursor-wait disabled:opacity-60"
                      >
                        {busy === "confirm" ? t("outfit.tags.working") : t("outfit.tags.confirm")}
                      </button>
                      <button
                        type="button"
                        disabled={busy !== null}
                        onClick={() =>
                          void run("reject", () =>
                            rejectOutfitMomentTag(momentId, tag.id),
                          )
                        }
                        className="border border-border px-3 py-2 text-caption text-text-secondary hover:bg-bg-secondary disabled:cursor-wait disabled:opacity-60"
                      >
                        {busy === "reject" ? t("outfit.tags.working") : t("outfit.tags.ignore")}
                      </button>
                      <button
                        type="button"
                        disabled={busy !== null}
                        onClick={() => beginEdit(tag)}
                        className="border border-border px-3 py-2 text-caption text-text-secondary hover:bg-bg-secondary disabled:cursor-wait disabled:opacity-60"
                      >
                        {t("outfit.tags.edit")}
                      </button>
                    </div>
                  </>
                )}
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="text-body text-text-secondary">{t("outfit.tags.empty")}</p>
      )}
    </section>
  );
}
