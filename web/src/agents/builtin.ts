import { getOutfitCapability } from "@/api/outfit";
import { createAgentRegistry } from "./registry";
import { outfitContribution } from "./outfitContribution";

function immutableCapabilityIds(ids: Iterable<string>): ReadonlySet<string> {
  const set = new Set(ids);
  const rejectMutation = () => {
    throw new TypeError("capability IDs are immutable");
  };
  Object.defineProperties(set, {
    add: { value: rejectMutation },
    clear: { value: rejectMutation },
    delete: { value: rejectMutation },
  });
  return Object.freeze(set);
}

const EMPTY_CAPABILITY_IDS = immutableCapabilityIds([]);

export const builtinAgentRegistry = createAgentRegistry([outfitContribution]);

/**
 * The shell only sees a successful capability ID after the authenticated
 * snapshot passed strict parsing and the private prerequisites are ready.
 */
export async function loadBuiltinAgentCapabilityIds(): Promise<ReadonlySet<string>> {
  try {
    const capability = await getOutfitCapability();
    if (
      capability.enabled &&
      capability.primaryPersonConfigured &&
      capability.storageReady
    ) {
      return immutableCapabilityIds([outfitContribution.capabilityId]);
    }
  } catch {
    // Capability discovery must never make the generic application fail open.
  }
  return EMPTY_CAPABILITY_IDS;
}
