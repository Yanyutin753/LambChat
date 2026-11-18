// Runs only inside the isolated native acceptance example, against the real toolbar and pipe.
(async () => {
  const invoke = (command, args = {}) => window.__TAURI_INTERNALS__.invoke(command, args);
  const sleep = () => new Promise((resolve) => setTimeout(resolve, 100));
  const wait = async (predicate) => {
    for (let i = 0; i < 100; i++) {
      if (await predicate()) return;
      await sleep();
    }
    throw new Error('Timed out waiting for native toolbar state');
  };
  const state = () => invoke('desktop_control_status', { ready: false });
  try {
    if (new URLSearchParams(location.search).get('surface') === 'overlay') {
      await wait(() => document.querySelector('.desktop-control-overlay'));
      const backgrounds = [document.documentElement, document.body, document.querySelector('.desktop-control-overlay')]
        .map(element => getComputedStyle(element).backgroundColor);
      if (!backgrounds.slice(0, 2).every(color => color === 'rgba(0, 0, 0, 0)'))
        throw new Error('Native overlay obscures desktop: ' + JSON.stringify(backgrounds));
      await wait(() => innerWidth === 308 && innerHeight === 38 && document.querySelector('.desktop-control-overlay').textContent);
      await invoke('desktop_control_status', {ready: false, report: {transparent: true}});
      return;
    }
    await wait(async () => (await invoke('desktop_control_status', {ready: false, report: {phase: "start"}})) !== 'mapping');
    await wait(() => document.querySelector('.desktop-control button'));
    const button = document.querySelector('.desktop-control button');
    const rect = button.getBoundingClientRect();
    if (rect.width < 36 || rect.height < 36 || rect.bottom > innerHeight)
      throw new Error('Toolbar button clipped or too small');
    for (let round = 0; round < 20; round++) {
      await wait(async () => (await state()) === 'active' && !button.disabled);
      button.click();
      await wait(async () => (await state()) === 'paused' && !button.disabled);
      const pausedRect = button.getBoundingClientRect();
      if (pausedRect.bottom > innerHeight || pausedRect.right > innerWidth)
        throw new Error('Expanded takeover controls are clipped');
      await invoke('desktop_control_status', {ready: false,report: {phase: 'paused', round, label: button.textContent}});
      // Wait for the React label and handler to observe the native acknowledgement.
      await sleep(); await sleep(); await sleep();
      if (document.querySelector('[role="alert"]')) throw new Error('Toolbar reported an IPC error');
      button.click();
      await wait(async () => ['idle', 'waiting', 'active', ...(round === 19 ? ['ended'] : [])].includes(await state()));
    }
    await wait(async () => (await state()) === 'ended');
    await invoke('desktop_control_status', {ready: false, report: { ok: true, pauseResumeRounds: 20, button: { width: rect.width, height: rect.height }, status: document.querySelector('[role="status"]').textContent } });
  } catch (error) {
    await invoke('desktop_control_status', {ready: false, report: { ok: false, error: String(error) } });
  }
})();
