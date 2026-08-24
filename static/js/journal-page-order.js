(() => {
  const journal = document.querySelector('[data-curated-journal]');
  if (!journal) return;

  const book = journal.querySelector('.journal-book');
  const venice = book?.querySelector('.curated-venice-sheet');
  const queenstown = book?.querySelector('.curated-queenstown-sheet');
  if (!book || !venice || !queenstown) return;

  // Swap only the physical journal order: Udaipur, NYC, Venice, Queenstown.
  book.insertBefore(venice, queenstown);
  venice.dataset.page = '2';
  queenstown.dataset.page = '3';

  const veniceNo = venice.querySelector('.venice-page-no');
  const queenstownNo = queenstown.querySelector('.qt-page-no');
  if (veniceNo) veniceNo.textContent = '03';
  if (queenstownNo) queenstownNo.textContent = '04';

  // Replace the controls so the original listener's cached page order cannot run.
  const oldPrev = journal.querySelector('[data-prev-page]');
  const oldNext = journal.querySelector('[data-next-page]');
  const indicator = journal.querySelector('[data-page-indicator]');
  if (!oldPrev || !oldNext || !indicator) return;

  const prev = oldPrev.cloneNode(true);
  const next = oldNext.cloneNode(true);
  oldPrev.replaceWith(prev);
  oldNext.replaceWith(next);

  const pages = [...book.querySelectorAll(':scope > [data-page]')];
  let current = 0;
  let animating = false;

  const sync = () => {
    pages.forEach((sheet, index) => {
      sheet.classList.toggle('active', index === current);
      sheet.classList.toggle('turned', index < current);
      sheet.classList.remove('flip-live');
      sheet.style.zIndex = index < current ? String(index + 1) : String(100 - index);
    });
    indicator.textContent = `PAGE ${String(current + 1).padStart(2, '0')}`;
    prev.disabled = current === 0 || animating;
    next.disabled = current === pages.length - 1 || animating;
  };

  const finish = (sheet) => {
    sheet.classList.remove('flip-live');
    animating = false;
    sync();
  };

  next.addEventListener('click', () => {
    if (animating || current >= pages.length - 1) return;
    animating = true;
    const leaving = pages[current];
    const entering = pages[current + 1];
    leaving.style.zIndex = '120';
    entering.style.zIndex = '110';
    leaving.classList.add('flip-live');
    prev.disabled = next.disabled = true;
    requestAnimationFrame(() => requestAnimationFrame(() => leaving.classList.add('turned')));
    current += 1;
    indicator.textContent = `PAGE ${String(current + 1).padStart(2, '0')}`;
    setTimeout(() => finish(leaving), 960);
  });

  prev.addEventListener('click', () => {
    if (animating || current <= 0) return;
    animating = true;
    const returning = pages[current - 1];
    const leaving = pages[current];
    returning.style.zIndex = '120';
    leaving.style.zIndex = '110';
    returning.classList.add('flip-live');
    prev.disabled = next.disabled = true;
    requestAnimationFrame(() => requestAnimationFrame(() => returning.classList.remove('turned')));
    current -= 1;
    indicator.textContent = `PAGE ${String(current + 1).padStart(2, '0')}`;
    setTimeout(() => finish(returning), 960);
  });

  sync();
})();
