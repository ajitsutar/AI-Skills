(() => {
  const scroller = document.getElementById("workspace") || document.scrollingElement;
  if (!scroller) return JSON.stringify({ ok: false, error: "missing scroller" });

  const amount = Math.max(
    700,
    Math.floor((scroller.clientHeight || window.innerHeight) * 0.85)
  );
  scroller.scrollBy(0, amount);
  return JSON.stringify({ ok: true, scrollTop: scroller.scrollTop });
})();
