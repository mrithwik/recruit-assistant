import type { ChangeEvent } from "react";

/**
 * Fix for a real React controlled-input gotcha: typing "0" then "2" into a
 * number field showing "0" produces the literal string "020" in the DOM.
 * `Number("020")` is 20, same as the number already in state, so React's
 * setState bails out (no state change) and never re-renders the input —
 * leaving "020" stuck on screen even though the underlying value is
 * correct. Forcing the DOM's own value back in sync (independent of
 * whether React re-renders) fixes it regardless of that bail-out.
 */
export function onNumberChange(setter: (n: number) => void) {
  return (e: ChangeEvent<HTMLInputElement>) => {
    const n = Number(e.target.value);
    if (Number.isNaN(n)) return;
    setter(n);
    e.target.value = String(n);
  };
}

export function selectOnFocus(e: { target: { select: () => void } }) {
  e.target.select();
}
