(() => {
  const videos = [...document.querySelectorAll('video')];
  videos.forEach(video => video.addEventListener('play', () => {
    videos.filter(other => other !== video).forEach(other => other.pause());
  }));
  const film = document.getElementById('film');
  if (!film) return;
  const status = document.getElementById('playback-status');
  let pendingSeek = null;
  const applySeek = () => {
    if (pendingSeek === null || film.readyState < 1 || !Number.isFinite(film.duration)) return;
    const time = Math.min(Math.max(pendingSeek, 0), film.duration);
    pendingSeek = null;
    film.currentTime = time;
    film.play().catch(() => { status.textContent = 'Chapter selected. Press Play to continue.'; });
  };
  document.querySelectorAll('[data-time]').forEach(button => {
    button.addEventListener('click', () => {
      pendingSeek = Number(button.dataset.time);
      if (!Number.isFinite(pendingSeek)) return;
      if (film.readyState < 1) {
        status.textContent = 'Loading the film…';
        film.load();
      }
      applySeek();
      film.scrollIntoView({block: 'center', behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'});
    });
  });
  film.addEventListener('loadedmetadata', applySeek);
  film.addEventListener('seeked', () => { status.textContent = ''; });
  film.addEventListener('playing', () => { status.textContent = ''; });
  film.addEventListener('error', () => {
    status.textContent = 'The film could not load. Use the Download MP4 link below, or open the local player from the source release.';
  });
  const chapters = [...document.querySelectorAll('.chapters [data-time]')];
  film.addEventListener('timeupdate', () => {
    let active = chapters[0];
    chapters.forEach(button => { if (Number(button.dataset.time) <= film.currentTime) active = button; });
    chapters.forEach(button => button === active ? button.setAttribute('aria-current', 'true') : button.removeAttribute('aria-current'));
  });
})();
