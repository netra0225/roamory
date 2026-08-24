(() => {
  'use strict';

  document.addEventListener('DOMContentLoaded', () => {
    const journal = document.querySelector('[data-journal]');
    if (!journal) return;

    const pages = [...journal.querySelectorAll('[data-page]')];
    const indicator = journal.querySelector('[data-page-indicator]');
    const arrows = journal.querySelectorAll('[data-prev-page], [data-next-page]');

    const syncPageLabel = () => {
      if (!indicator) return;
      const activeIndex = pages.findIndex((page) => page.classList.contains('active'));
      const pageNumber = activeIndex >= 0 ? activeIndex + 1 : 1;
      indicator.textContent = `PAGE ${String(pageNumber).padStart(2, '0')}`;
    };

    requestAnimationFrame(syncPageLabel);
    arrows.forEach((arrow) => {
      arrow.addEventListener('click', () => requestAnimationFrame(syncPageLabel));
    });
  });
})();
