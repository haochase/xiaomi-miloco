import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { deleteOutfitMedia, outfitMediaUrl } from "@/api";
import { toast } from "@/components/Toast";
import {
  fetchOutfitPhoto,
  shareOrDownloadOutfitPhoto,
  type MediaAction,
} from "@/lib/outfitMedia";

type MediaActionWithDelete = MediaAction | "delete";

interface Props {
  assetId: string;
  onDeleted: () => Promise<void>;
}

export function OutfitMediaActions({ assetId, onDeleted }: Props) {
  const { t } = useTranslation();
  const [busy, setBusy] = useState<MediaActionWithDelete | null>(null);
  const url = outfitMediaUrl(assetId);

  const act = async (action: MediaAction) => {
    setBusy(action);
    try {
      const result = await shareOrDownloadOutfitPhoto({
        url,
        filename: "outfit-moment-photo.jpg",
        title: t("outfit.media.shareTitle"),
        action,
      });
      if (result === "shared") {
        toast(t("outfit.media.shared"), "ok");
      } else if (result === "downloaded") {
        toast(t("outfit.media.downloaded"), "ok");
      }
    } catch {
      toast(t("outfit.media.actionFailed"), "warn");
    } finally {
      setBusy(null);
    }
  };

  const remove = async () => {
    if (!window.confirm(t("outfit.media.deleteConfirm"))) {
      return;
    }
    setBusy("delete");
    try {
      await deleteOutfitMedia(assetId);
      await onDeleted();
      toast(t("outfit.media.deleted"), "ok");
    } catch {
      toast(t("outfit.media.deleteFailed"), "warn");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-3">
      <PrivateOutfitImage src={url} alt={t("outfit.media.alt")} />
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={busy !== null}
          onClick={() => act("share")}
          className="border border-border px-3 py-2 text-caption text-text-secondary hover:bg-bg-secondary disabled:cursor-wait disabled:opacity-60"
        >
          {busy === "share" ? t("outfit.media.working") : t("outfit.media.share")}
        </button>
        <button
          type="button"
          disabled={busy !== null}
          onClick={() => act("download")}
          className="border border-border px-3 py-2 text-caption text-text-secondary hover:bg-bg-secondary disabled:cursor-wait disabled:opacity-60"
        >
          {busy === "download" ? t("outfit.media.working") : t("outfit.media.save")}
        </button>
        <button
          type="button"
          disabled={busy !== null}
          onClick={() => void remove()}
          className="border border-border px-3 py-2 text-caption text-text-secondary hover:bg-bg-secondary disabled:cursor-wait disabled:opacity-60"
        >
          {busy === "delete" ? t("outfit.media.working") : t("outfit.media.delete")}
        </button>
      </div>
    </div>
  );
}

function PrivateOutfitImage({ src, alt }: { src: string; alt: string }) {
  const { t } = useTranslation();
  const [objectUrl, setObjectUrl] = useState<string>();
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let nextUrl: string | undefined;
    setObjectUrl(undefined);
    setFailed(false);
    void fetchOutfitPhoto(src)
      .then((blob) => {
        if (cancelled) {
          return;
        }
        nextUrl = URL.createObjectURL(blob);
        setObjectUrl(nextUrl);
      })
      .catch(() => {
        if (!cancelled) {
          setFailed(true);
        }
      });
    return () => {
      cancelled = true;
      if (nextUrl) {
        URL.revokeObjectURL(nextUrl);
      }
    };
  }, [src]);

  if (failed) {
    return <p className="text-caption text-text-secondary">{t("outfit.media.previewUnavailable")}</p>;
  }
  if (!objectUrl) {
    return <p className="text-caption text-text-tertiary">{t("outfit.media.previewLoading")}</p>;
  }
  return <img src={objectUrl} alt={alt} className="max-h-96 w-full object-contain" />;
}
