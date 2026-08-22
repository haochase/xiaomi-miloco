import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { IconCamera } from "@/lib/icons";
import {
  requestVisualReview,
  type VisualReviewResult,
  type VisualReviewStatus,
  type VisualReviewTrigger,
} from "@/api";

type ReviewDisplayStatus = "idle" | "evaluating" | VisualReviewStatus;
type VisualReviewRequest = (
  trigger: VisualReviewTrigger,
) => Promise<VisualReviewResult>;

export interface VisualReviewSessionSelection {
  readonly key: string | undefined;
  readonly generation: number;
}

export interface VisualReviewSessionTicket {
  readonly key: string;
  readonly generation: number;
  readonly trigger: VisualReviewTrigger;
}

export type VisualReviewSessionCompletion =
  | {
      readonly kind: "result";
      readonly ticket: VisualReviewSessionTicket;
      readonly result: VisualReviewResult;
    }
  | {
      readonly kind: "failed";
      readonly ticket: VisualReviewSessionTicket;
    }
  | {
      readonly kind: "stale";
      readonly ticket: VisualReviewSessionTicket;
    };

export interface VisualReviewSessionController {
  synchronize(trigger: VisualReviewTrigger | undefined): VisualReviewSessionSelection;
  current(): VisualReviewSessionSelection;
  isCurrent(ticket: VisualReviewSessionTicket): boolean;
  begin():
    | {
        readonly ticket: VisualReviewSessionTicket;
        readonly completion: Promise<VisualReviewSessionCompletion>;
      }
    | undefined;
}

interface ActiveVisualReviewSelection extends VisualReviewSessionSelection {
  readonly key: string;
  readonly trigger: VisualReviewTrigger;
  requested: boolean;
}

interface ReviewViewState extends VisualReviewSessionSelection {
  readonly status: ReviewDisplayStatus;
  readonly requestFailed: boolean;
  readonly attempted: boolean;
}

interface Props {
  trigger?: VisualReviewTrigger;
}

export function visualReviewStatusKey(
  status: Exclude<ReviewDisplayStatus, "idle">,
): string {
  return `agents.outfit.review.status.${status}`;
}

export function visualReviewSelectionKey(trigger: VisualReviewTrigger): string {
  return JSON.stringify([
    trigger.triggerId,
    trigger.recommendationId,
    trigger.deviceId,
  ]);
}

function viewStateFor(
  selection: VisualReviewSessionSelection,
  state: Omit<ReviewViewState, "key" | "generation"> = {
    status: "idle",
    requestFailed: false,
    attempted: false,
  },
): ReviewViewState {
  return {
    key: selection.key,
    generation: selection.generation,
    ...state,
  };
}

function isViewStateCurrent(
  state: ReviewViewState,
  selection: VisualReviewSessionSelection,
): boolean {
  return state.key === selection.key && state.generation === selection.generation;
}

export function createVisualReviewSessionController(
  request: VisualReviewRequest = requestVisualReview,
): VisualReviewSessionController {
  let generation = 0;
  let active: ActiveVisualReviewSelection | undefined;

  const current = (): VisualReviewSessionSelection => ({
    key: active?.key,
    generation,
  });

  const isCurrent = (ticket: VisualReviewSessionTicket): boolean =>
    active?.key === ticket.key && active.generation === ticket.generation;

  const settle = async (
    ticket: VisualReviewSessionTicket,
  ): Promise<VisualReviewSessionCompletion> => {
    try {
      const result = await request(ticket.trigger);
      return isCurrent(ticket)
        ? { kind: "result", ticket, result }
        : { kind: "stale", ticket };
    } catch {
      return isCurrent(ticket)
        ? { kind: "failed", ticket }
        : { kind: "stale", ticket };
    }
  };

  return {
    synchronize: (trigger) => {
      const key = trigger ? visualReviewSelectionKey(trigger) : undefined;
      if (
        (active === undefined && key === undefined) ||
        (active !== undefined && active.key === key)
      ) {
        return current();
      }

      generation += 1;
      if (!trigger) {
        active = undefined;
        return current();
      }

      active = {
        key: visualReviewSelectionKey(trigger),
        generation,
        trigger,
        requested: false,
      };
      return current();
    },
    current,
    isCurrent,
    begin: () => {
      if (!active || active.requested) return undefined;

      active.requested = true;
      const ticket: VisualReviewSessionTicket = {
        key: active.key,
        generation: active.generation,
        trigger: active.trigger,
      };
      return { ticket, completion: settle(ticket) };
    },
  };
}

export function createVisualReviewSession(
  trigger: VisualReviewTrigger,
  request: VisualReviewRequest = requestVisualReview,
): VisualReviewSessionController {
  const controller = createVisualReviewSessionController(request);
  controller.synchronize(trigger);
  return controller;
}

export function OutfitTryOnReview({ trigger }: Props) {
  const { t } = useTranslation();
  if (!trigger) {
    return (
      <p className="text-body text-text-secondary">
        {t("agents.outfit.review.noSelection")}
      </p>
    );
  }

  return (
    <OutfitTryOnReviewSession
      key={visualReviewSelectionKey(trigger)}
      trigger={trigger}
    />
  );
}

function OutfitTryOnReviewSession({ trigger }: { trigger: VisualReviewTrigger }) {
  const { t } = useTranslation();
  const sessionKey = visualReviewSelectionKey(trigger);
  const [controller] = useState(() => createVisualReviewSession(trigger));
  const selection = controller.current();
  const [savedViewState, setViewState] = useState<ReviewViewState>(() =>
    viewStateFor(selection),
  );
  const viewState = isViewStateCurrent(savedViewState, selection)
    ? savedViewState
    : viewStateFor(selection);

  useEffect(() => {
    // The initializer makes the first committed button ready before effects run.
    // This setup also restores the local session after StrictMode's dev cleanup.
    controller.synchronize(trigger);
    return () => {
      controller.synchronize(undefined);
    };
  }, [controller, sessionKey]);

  const requestReview = async () => {
    const run = controller.begin();
    if (!run || !controller.isCurrent(run.ticket)) return;

    setViewState(
      viewStateFor(run.ticket, {
        status: "evaluating",
        requestFailed: false,
        attempted: true,
      }),
    );
    const completion = await run.completion;
    if (completion.kind === "stale" || !controller.isCurrent(completion.ticket)) {
      return;
    }

    if (completion.kind === "result") {
      if (!controller.isCurrent(completion.ticket)) return;
      setViewState(
        viewStateFor(completion.ticket, {
          status: completion.result.status,
          requestFailed: false,
          attempted: true,
        }),
      );
      return;
    }

    if (!controller.isCurrent(completion.ticket)) return;
    setViewState(
      viewStateFor(completion.ticket, {
        status: "idle",
        requestFailed: true,
        attempted: true,
      }),
    );
  };

  return (
    <div className="space-y-3">
      <button
        type="button"
        onClick={requestReview}
        disabled={viewState.attempted}
        className="inline-flex min-h-9 items-center gap-2 rounded-md border border-border px-3 py-2 text-body text-text-primary transition-colors hover:border-border-strong disabled:cursor-not-allowed disabled:opacity-60"
      >
        <IconCamera aria-hidden />
        <span>{t("agents.outfit.review.request")}</span>
      </button>
      {viewState.status !== "idle" && (
        <p className="text-body text-text-secondary" role="status">
          {t(visualReviewStatusKey(viewState.status))}
        </p>
      )}
      {viewState.requestFailed && (
        <p className="text-body text-status-warning" role="alert">
          {t("agents.outfit.review.unavailable")}
        </p>
      )}
    </div>
  );
}
