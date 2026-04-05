import { useEffect, useRef, useState } from "react";
import type { DragEvent } from "react";
import { Button } from "antd";
import lottie, { type AnimationItem } from "lottie-web";

import petAnimationData from "../../assets/lottie/loader-cat.json";

type MoveState = {
  isMoving: boolean;
  movedDistance: number;
  activePointerId: number | null;
};

function normalizeDroppedPath(input: string): string {
  const raw = String(input || "").trim();
  if (!raw) return "";
  const firstLine = raw
    .split(/\r?\n/)
    .map((line) => line.trim())
    .find(Boolean);
  if (!firstLine) return "";

  if (/^file:\/\//i.test(firstLine)) {
    try {
      let parsed = decodeURIComponent(firstLine.replace(/^file:\/+?/i, ""));
      parsed = parsed.replace(/^localhost\//i, "");
      if (/^[A-Za-z]:/.test(parsed)) {
        return parsed;
      }
      return parsed.startsWith("/") ? parsed : `/${parsed}`;
    } catch {
      return "";
    }
  }

  if (/^[A-Za-z]:[\\/]/.test(firstLine)) {
    return firstLine;
  }

  return "";
}

function extractDropPath(event: DragEvent<HTMLDivElement>): string {
  const dataTransfer = event.dataTransfer;
  if (!dataTransfer) return "";

  const uriList = normalizeDroppedPath(dataTransfer.getData("text/uri-list"));
  if (uriList) return uriList;

  const plainText = normalizeDroppedPath(dataTransfer.getData("text/plain"));
  if (plainText) return plainText;

  const files = dataTransfer.files ? Array.from(dataTransfer.files) : [];
  const first = files.length > 0 ? files[0] : null;
  const filePath = first && first.path ? String(first.path).trim() : "";
  return filePath;
}

export function PetWindow() {
  const buttonRef = useRef<HTMLButtonElement>(null);
  const lottieRef = useRef<HTMLDivElement>(null);
  const lottieInstanceRef = useRef<AnimationItem | null>(null);
  const moveStateRef = useRef<MoveState>({
    isMoving: false,
    movedDistance: 0,
    activePointerId: null,
  });
  const [dragOver, setDragOver] = useState(false);

  useEffect(() => {
    document.body.classList.add("pet-route-body");
    const previousTitle = document.title;
    document.title = "桌宠";
    return () => {
      document.body.classList.remove("pet-route-body");
      document.title = previousTitle;
    };
  }, []);

  useEffect(() => {
    if (!lottieRef.current) return;
    lottieInstanceRef.current = lottie.loadAnimation({
      container: lottieRef.current,
      renderer: "svg",
      loop: true,
      autoplay: true,
      animationData: petAnimationData,
      rendererSettings: {
        preserveAspectRatio: "xMidYMid meet",
      },
    });

    return () => {
      lottieInstanceRef.current?.destroy();
      lottieInstanceRef.current = null;
    };
  }, []);

  useEffect(() => {
    const button = buttonRef.current;
    if (!button) return;

    const onPointerMove = (event: PointerEvent) => {
      const state = moveStateRef.current;
      if (!state.isMoving) return;
      if (state.activePointerId !== null && event.pointerId !== state.activePointerId) return;

      state.movedDistance += Math.abs(event.movementX) + Math.abs(event.movementY);
      if (window.petApi && typeof window.petApi.moveTo === "function") {
        window.petApi.moveTo(event.screenX, event.screenY).catch(() => undefined);
      }
    };

    const stopMoving = (event?: PointerEvent) => {
      const state = moveStateRef.current;
      if (!state.isMoving) return;
      if (event && state.activePointerId !== null && event.pointerId !== state.activePointerId) return;

      state.isMoving = false;
      if (state.activePointerId !== null) {
        try {
          button.releasePointerCapture(state.activePointerId);
        } catch {
          // ignore pointer capture errors
        }
      }
      state.activePointerId = null;

      if (window.petApi && typeof window.petApi.endMove === "function") {
        window.petApi.endMove().catch(() => undefined);
      }

      if (state.movedDistance < 6 && window.petApi && typeof window.petApi.openChatWindow === "function") {
        window.petApi.openChatWindow().catch(() => undefined);
      }
    };

    const onPointerDown = (event: PointerEvent) => {
      if (event.button !== 0) return;
      const state = moveStateRef.current;

      try {
        button.setPointerCapture(event.pointerId);
      } catch {
        // ignore pointer capture errors
      }

      state.movedDistance = 0;
      state.isMoving = true;
      state.activePointerId = event.pointerId;

      if (window.petApi && typeof window.petApi.beginMove === "function") {
        window.petApi.beginMove(event.screenX, event.screenY).catch(() => undefined);
      }
    };

    button.addEventListener("pointerdown", onPointerDown);
    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", stopMoving);
    window.addEventListener("pointercancel", stopMoving);

    return () => {
      button.removeEventListener("pointerdown", onPointerDown);
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", stopMoving);
      window.removeEventListener("pointercancel", stopMoving);
    };
  }, []);

  const onDrop = async (event: DragEvent<HTMLButtonElement>) => {
    event.preventDefault();
    setDragOver(false);

    const dropPath = extractDropPath(event);
    if (!dropPath) return;

    if (window.petApi && typeof window.petApi.setWorkspaceDir === "function") {
      const result = await window.petApi.setWorkspaceDir(dropPath);
      if (!result || !result.ok) {
        window.alert((result && result.message) || "目录绑定失败");
        return;
      }
      if (typeof window.petApi.openChatWindow === "function") {
        await window.petApi.openChatWindow();
      }
    }
  };

  const onDoubleClick = async () => {
    if (window.petApi && typeof window.petApi.pickWorkspaceDir === "function") {
      await window.petApi.pickWorkspaceDir();
    }
  };

  return (
    <div className="pet-window-root" onDoubleClick={onDoubleClick}>
      <Button
        ref={buttonRef}
        className={`pet-window-button${dragOver ? " drag-over" : ""}`}
        onDragOver={(event) => {
          event.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
        role="button"
        aria-label="打开桌宠聊天"
      >
        <div className="pet-window-aura" />
        <div className="pet-window-lottie" ref={lottieRef} />
      </Button>
    </div>
  );
}
