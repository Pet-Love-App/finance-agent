import type { TemplateApi } from "../electron/preload";
import type { PetApi } from "../electron/petPreload";
import type { PetChatApi } from "../electron/petChatPreload";

declare global {
  interface Window {
    templateApi?: TemplateApi;
    petApi?: PetApi;
    petChatApi?: PetChatApi;
  }
}

export {};
