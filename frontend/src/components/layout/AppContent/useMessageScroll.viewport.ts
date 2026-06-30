import {
  getAutoScrollResumeThresholdPx,
  getAwayFromBottomThresholdPx,
} from "./messageScrollUtils";

const MOBILE_BOTTOM_BREATHING_ROOM_PX = 96;
const DESKTOP_BOTTOM_BREATHING_ROOM_PX = 16;

export interface MessageScrollViewportState {
  isMobileViewport: boolean;
  bottomBreathingRoomPx: number;
  awayFromBottomThresholdPx: number;
  autoScrollResumeThresholdPx: number;
}

export function getMessageScrollViewportState(): MessageScrollViewportState {
  const isMobileViewport =
    typeof window !== "undefined" ? window.innerWidth < 640 : false;
  const bottomBreathingRoomPx = isMobileViewport
    ? MOBILE_BOTTOM_BREATHING_ROOM_PX
    : DESKTOP_BOTTOM_BREATHING_ROOM_PX;

  return {
    isMobileViewport,
    bottomBreathingRoomPx,
    awayFromBottomThresholdPx: getAwayFromBottomThresholdPx(
      isMobileViewport,
      bottomBreathingRoomPx,
    ),
    autoScrollResumeThresholdPx: getAutoScrollResumeThresholdPx(
      isMobileViewport,
      bottomBreathingRoomPx,
    ),
  };
}
