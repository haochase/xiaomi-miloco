import { FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  confirmOutfitWardrobeDraft,
  createOutfitWardrobeDraft,
  deleteOutfitWardrobeItem,
  discardOutfitWardrobeDraft,
  listOutfitWardrobe,
  listOutfitWardrobeDrafts,
  updateOutfitWardrobeItem,
} from "@/api";
import { toast } from "@/components/Toast";
import { useAsync } from "@/hooks/useAsync";
import type {
  OutfitWardrobeCategory,
  OutfitWardrobeItem,
} from "@/lib/types";

const CATEGORIES: OutfitWardrobeCategory[] = [
  "top",
  "bottom",
  "dress",
  "outerwear",
  "shoes",
  "bag",
  "accessory",
];

export function OutfitWardrobeView() {
  const { t } = useTranslation();
  const wardrobe = useAsync(listOutfitWardrobe, [], {
    errorLabel: t("outfit.wardrobe.loadError"),
  });
  const drafts = useAsync(listOutfitWardrobeDrafts, [], {
    errorLabel: t("outfit.wardrobe.loadError"),
  });
  const [name, setName] = useState("");
  const [category, setCategory] = useState<OutfitWardrobeCategory>("top");
  const [sourceReference, setSourceReference] = useState("");
  const [busy, setBusy] = useState(false);

  const reload = async () => {
    await Promise.all([wardrobe.reload(), drafts.reload()]);
  };

  const run = async (action: () => Promise<void>, successMessage: string) => {
    setBusy(true);
    try {
      await action();
      await reload();
      toast(successMessage, "ok");
    } catch (error) {
      toast(
        error instanceof Error ? error.message : t("outfit.wardrobe.actionFailed"),
        "warn",
      );
    } finally {
      setBusy(false);
    }
  };

  const submitDraft = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmedName = name.trim();
    const trimmedSource = sourceReference.trim();
    if (!trimmedName || !trimmedSource) {
      toast(t("outfit.wardrobe.required"), "warn");
      return;
    }
    void run(async () => {
      await createOutfitWardrobeDraft({
        name: trimmedName,
        category,
        sourceType: "manual",
        sourceReference: trimmedSource,
      });
      setName("");
      setSourceReference("");
    }, t("outfit.wardrobe.draftCreated"));
  };

  return (
    <section className="space-y-6" aria-labelledby="outfit-wardrobe-title">
      <div className="space-y-1">
        <h2 id="outfit-wardrobe-title" className="text-section-title text-text-primary">
          {t("outfit.wardrobe.title")}
        </h2>
        <p className="text-body text-text-secondary">{t("outfit.wardrobe.hint")}</p>
      </div>

      <form
        className="grid gap-3 border border-border bg-bg-secondary p-4 sm:grid-cols-2"
        onSubmit={submitDraft}
      >
        <label className="grid gap-1 text-caption text-text-secondary">
          {t("outfit.wardrobe.name")}
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
            className="min-h-10 border border-border bg-bg-primary px-3 text-body text-text-primary"
            maxLength={120}
          />
        </label>
        <label className="grid gap-1 text-caption text-text-secondary">
          {t("outfit.wardrobe.category")}
          <select
            value={category}
            onChange={(event) => setCategory(event.target.value as OutfitWardrobeCategory)}
            className="min-h-10 border border-border bg-bg-primary px-3 text-body text-text-primary"
          >
            {CATEGORIES.map((item) => (
              <option key={item} value={item}>
                {t(`outfit.wardrobe.categories.${item}`)}
              </option>
            ))}
          </select>
        </label>
        <label className="grid gap-1 text-caption text-text-secondary sm:col-span-2">
          {t("outfit.wardrobe.sourceReference")}
          <input
            value={sourceReference}
            onChange={(event) => setSourceReference(event.target.value)}
            className="min-h-10 border border-border bg-bg-primary px-3 text-body text-text-primary"
            maxLength={240}
          />
        </label>
        <div className="sm:col-span-2">
          <button
            type="submit"
            disabled={busy}
            className="min-h-10 border border-brand-primary bg-brand-primary px-4 text-body text-white disabled:opacity-60"
          >
            {busy ? t("outfit.wardrobe.working") : t("outfit.wardrobe.add")}
          </button>
        </div>
      </form>

      {drafts.data?.length ? (
        <section className="space-y-3" aria-labelledby="outfit-wardrobe-drafts-title">
          <h3 id="outfit-wardrobe-drafts-title" className="text-title text-text-primary">
            {t("outfit.wardrobe.pendingTitle")}
          </h3>
          <ul className="grid gap-px border border-border bg-border">
            {drafts.data.map((draft) => (
              <li key={draft.id} className="flex flex-wrap items-center gap-3 bg-bg-primary p-3">
                <div className="min-w-0 grow">
                  <p className="break-words text-body text-text-primary">{draft.name}</p>
                  <p className="break-words text-caption text-text-tertiary">
                    {t(`outfit.wardrobe.categories.${draft.category}`)} · {draft.sourceReference}
                  </p>
                </div>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() =>
                    void run(
                      () => confirmOutfitWardrobeDraft(draft.id).then(() => undefined),
                      t("outfit.wardrobe.confirmed"),
                    )
                  }
                  className="min-h-9 border border-border px-3 text-caption text-text-primary disabled:opacity-60"
                >
                  {t("outfit.wardrobe.confirm")}
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => {
                    if (window.confirm(t("outfit.wardrobe.discardConfirm"))) {
                      void run(
                        () => discardOutfitWardrobeDraft(draft.id),
                        t("outfit.wardrobe.discarded"),
                      );
                    }
                  }}
                  className="min-h-9 border border-border px-3 text-caption text-text-secondary disabled:opacity-60"
                >
                  {t("outfit.wardrobe.discard")}
                </button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <WardrobeInventory
        items={wardrobe.data ?? []}
        busy={busy}
        onEdit={(item) => {
          const nextName = window.prompt(t("outfit.wardrobe.editName"), item.name);
          if (nextName === null || nextName.trim() === "" || nextName.trim() === item.name) {
            return;
          }
          void run(
            () => updateOutfitWardrobeItem(item.id, { name: nextName.trim() }).then(() => undefined),
            t("outfit.wardrobe.updated"),
          );
        }}
        onDelete={(item) => {
          if (window.confirm(t("outfit.wardrobe.deleteConfirm", { name: item.name }))) {
            void run(
              () => deleteOutfitWardrobeItem(item.id),
              t("outfit.wardrobe.deleted"),
            );
          }
        }}
      />
    </section>
  );
}

interface WardrobeInventoryProps {
  items: OutfitWardrobeItem[];
  busy: boolean;
  onEdit: (item: OutfitWardrobeItem) => void;
  onDelete: (item: OutfitWardrobeItem) => void;
}

function WardrobeInventory({ items, busy, onEdit, onDelete }: WardrobeInventoryProps) {
  const { t } = useTranslation();
  return (
    <section className="space-y-3" aria-labelledby="outfit-wardrobe-inventory-title">
      <h3 id="outfit-wardrobe-inventory-title" className="text-title text-text-primary">
        {t("outfit.wardrobe.inventoryTitle")}
      </h3>
      {items.length ? (
        <ul className="grid gap-px border border-border bg-border sm:grid-cols-2">
          {items.map((item) => (
            <li key={item.id} className="flex min-h-28 flex-col gap-3 bg-bg-primary p-4">
              <div className="min-w-0 grow">
                <p className="break-words text-body text-text-primary">{item.name}</p>
                <p className="break-words text-caption text-text-tertiary">
                  {t(`outfit.wardrobe.categories.${item.category}`)} · {item.sourceReference}
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => onEdit(item)}
                  className="min-h-9 border border-border px-3 text-caption text-text-primary disabled:opacity-60"
                >
                  {t("outfit.wardrobe.edit")}
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => onDelete(item)}
                  className="min-h-9 border border-border px-3 text-caption text-text-secondary disabled:opacity-60"
                >
                  {t("outfit.wardrobe.delete")}
                </button>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p className="py-8 text-center text-body text-text-secondary">
          {t("outfit.wardrobe.empty")}
        </p>
      )}
    </section>
  );
}
