(() => {
  'use strict';

  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // Accessible confirmation dialog for destructive server actions.
  const dialog = document.querySelector('#confirmDialog');
  let pendingForm = null;
  if (dialog) {
    const message = dialog.querySelector('#confirmMessage');
    const cancel = dialog.querySelector('[data-dialog-cancel]');
    const confirm = dialog.querySelector('[data-dialog-confirm]');
    document.querySelectorAll('form[data-confirm]').forEach((form) => {
      form.addEventListener('submit', (event) => {
        if (form.dataset.confirmed === 'true') return;
        event.preventDefault();
        pendingForm = form;
        message.textContent = form.dataset.confirm || 'This action cannot be undone.';
        dialog.showModal();
      });
    });
    cancel.addEventListener('click', () => { pendingForm = null; dialog.close(); });
    confirm.addEventListener('click', () => {
      if (!pendingForm) return dialog.close();
      pendingForm.dataset.confirmed = 'true';
      const form = pendingForm;
      pendingForm = null;
      dialog.close();
      form.requestSubmit();
    });
    dialog.addEventListener('cancel', () => { pendingForm = null; });
  }

  // Lightweight loading state; backend validation remains authoritative.
  document.querySelectorAll('form[data-loading-form]').forEach((form) => {
    form.addEventListener('submit', () => {
      const submit = form.querySelector('button[type="submit"]');
      if (!submit) return;
      submit.dataset.label = submit.textContent;
      submit.textContent = 'Saving…';
      submit.setAttribute('aria-busy', 'true');
    });
  });

  // Flash-driven state animations.
  const flashTypes = [...document.querySelectorAll('[data-flash]')].map((el) => el.dataset.flash);
  if (flashTypes.includes('stamp')) {
    const stage = document.querySelector('[data-stamp-stage]');
    if (stage && !reducedMotion) {
      stage.classList.add('show');
      window.setTimeout(() => stage.classList.remove('show'), 900);
    }
  }
  if (flashTypes.includes('wallet')) {
    const wallet = document.querySelector('[data-wallet-stage]');
    if (wallet && !reducedMotion) {
      wallet.classList.add('animate');
      window.setTimeout(() => wallet.classList.remove('animate'), 1200);
    }
  }
  if (flashTypes.includes('develop')) {
    const firstPage = document.querySelector('.journal-sheet.active');
    if (firstPage && !reducedMotion) firstPage.classList.add('developing');
  }
  if (flashTypes.includes('pack')) {
    const suitcase = document.querySelector('.suitcase-illustration');
    if (suitcase && !reducedMotion) suitcase.classList.add('just-packed');
  }
  if (flashTypes.includes('stamp')) {
    const route = document.querySelector('[data-route]');
    if (route && !reducedMotion) route.classList.add('route-just-progressed');
  }

  // Journal book: front/back layering and actual 3D spine rotation.
  const journal = document.querySelector('[data-journal]');
  if (journal) {
    const pages = [...journal.querySelectorAll('[data-page]')];
    const next = journal.querySelector('[data-next-page]');
    const prev = journal.querySelector('[data-prev-page]');
    const indicator = journal.querySelector('[data-page-indicator]');
    let page = 0;

    const render = () => {
      pages.forEach((sheet, index) => {
        sheet.classList.toggle('turned', index < page);
        sheet.classList.toggle('active', index === page);
        sheet.style.zIndex = index < page ? index : pages.length - index;
      });
      if (indicator) indicator.textContent = `${Math.min(page + 1, pages.length)} / ${pages.length}`;
      if (prev) prev.disabled = page === 0;
      if (next) next.disabled = page >= pages.length - 1;
    };
    next?.addEventListener('click', () => { if (page < pages.length - 1) { page += 1; render(); } });
    prev?.addEventListener('click', () => { if (page > 0) { page -= 1; render(); } });
    render();
  }

  // Create/Edit Trip wizard: details → cover → review → submit.
  const tripWizard = document.querySelector('[data-trip-wizard]');
  if (tripWizard) {
    const panels = [...tripWizard.querySelectorAll('[data-wizard-step]')];
    const indicators = [...tripWizard.querySelectorAll('[data-wizard-indicator]')];
    const nextButton = tripWizard.querySelector('[data-wizard-next]');
    const backButton = tripWizard.querySelector('[data-wizard-back]');
    const submitButton = tripWizard.querySelector('[data-wizard-submit]');
    const coverInput = tripWizard.querySelector('[data-cover-input]');
    const coverPreview = tripWizard.querySelector('[data-cover-preview]');
    const coverPlaceholder = tripWizard.querySelector('[data-cover-placeholder]');
    let step = 1;

    const field = (name) => tripWizard.elements.namedItem(name);
    const text = (name) => (field(name)?.value || '').trim();
    const setText = (selector, value, fallback = '—') => {
      const el = tripWizard.querySelector(selector);
      if (el) el.textContent = value || fallback;
    };

    const syncReview = () => {
      const start = text('start_date');
      const end = text('end_date');
      setText('[data-preview-destination]', text('destination'), 'Destination');
      setText('[data-preview-dates]', start && end ? `${start} → ${end}` : '', 'Dates');
      setText('[data-review-title]', text('title'), 'Your trip title');
      setText('[data-review-description]', text('description'), 'A trip ready for its own story.');
      setText('[data-review-destination]', text('destination'));
      setText('[data-review-dates]', start && end ? `${start} → ${end}` : '');
      const budget = Number(field('planned_budget')?.value || 0);
      setText('[data-review-budget]', `₹${Number.isFinite(budget) ? budget.toLocaleString('en-IN', {maximumFractionDigits: 0}) : '0'}`);
    };

    const validateStepOne = () => {
      const required = [...panels[0].querySelectorAll('input[required], textarea[required], select[required]')];
      const start = field('start_date');
      const end = field('end_date');
      if (end) end.setCustomValidity('');
      if (start?.value && end?.value && end.value < start.value) {
        end.setCustomValidity('End date cannot be before start date.');
      }
      for (const input of required) {
        if (!input.checkValidity()) {
          input.reportValidity();
          return false;
        }
      }
      if (end && !end.checkValidity()) {
        end.reportValidity();
        return false;
      }
      return true;
    };

    const renderWizard = () => {
      panels.forEach((panel, index) => {
        const active = index + 1 === step;
        panel.hidden = !active;
        panel.classList.toggle('active', active);
      });
      indicators.forEach((indicator, index) => {
        const n = index + 1;
        indicator.classList.toggle('active', n === step);
        indicator.classList.toggle('done', n < step);
      });
      if (backButton) backButton.hidden = step === 1;
      if (nextButton) nextButton.hidden = step === 3;
      if (submitButton) submitButton.hidden = step !== 3;
      syncReview();
      tripWizard.scrollIntoView({behavior: reducedMotion ? 'auto' : 'smooth', block: 'start'});
    };

    nextButton?.addEventListener('click', () => {
      if (step === 1 && !validateStepOne()) return;
      if (step < 3) step += 1;
      renderWizard();
    });
    backButton?.addEventListener('click', () => {
      if (step > 1) step -= 1;
      renderWizard();
    });

    coverInput?.addEventListener('change', () => {
      const file = coverInput.files?.[0];
      if (!file || !coverPreview) return;
      const reader = new FileReader();
      reader.addEventListener('load', () => {
        coverPreview.style.backgroundImage = `url("${reader.result}")`;
        if (coverPlaceholder) coverPlaceholder.textContent = '';
      });
      reader.readAsDataURL(file);
    });

    ['title','destination','description','planned_budget','start_date','end_date'].forEach((name) => {
      field(name)?.addEventListener('input', syncReview);
      field(name)?.addEventListener('change', syncReview);
    });
    renderWizard();
  }

  // Travel Wallet staged upload: choose → preview → explicit confirm.
  const walletFile = document.querySelector('[data-wallet-file]');
  const walletPreview = document.querySelector('[data-wallet-preview]');
  if (walletFile && walletPreview) {
    const nameEl = walletPreview.querySelector('[data-wallet-preview-name]');
    const metaEl = walletPreview.querySelector('[data-wallet-preview-meta]');
    const thumb = walletPreview.querySelector('[data-wallet-preview-thumb]');
    walletFile.addEventListener('change', () => {
      const file = walletFile.files?.[0];
      if (!file) {
        walletPreview.hidden = true;
        return;
      }
      walletPreview.hidden = false;
      if (nameEl) nameEl.textContent = file.name;
      if (metaEl) metaEl.textContent = `${(file.size / 1024).toFixed(file.size > 1024 * 1024 ? 0 : 1)} KB · ${file.type || 'document'}`;
      if (thumb) {
        thumb.replaceChildren();
        if (file.type.startsWith('image/')) {
          const image = document.createElement('img');
          image.alt = '';
          const reader = new FileReader();
          reader.addEventListener('load', () => { image.src = reader.result; });
          reader.readAsDataURL(file);
          thumb.appendChild(image);
        } else {
          const label = document.createElement('span');
          label.textContent = file.name.split('.').pop()?.toUpperCase() || 'FILE';
          thumb.appendChild(label);
        }
      }
    });
  }

  const memoryDialog = document.querySelector('[data-memory-dialog]');
  document.querySelectorAll('[data-open-memory-form]').forEach((button) => {
    button.addEventListener('click', () => memoryDialog?.showModal());
  });
  document.querySelector('[data-close-memory-form]')?.addEventListener('click', () => memoryDialog?.close());

  // Keep flash messages from covering the app indefinitely.
  window.setTimeout(() => {
    document.querySelectorAll('.flash').forEach((flash) => {
      flash.style.opacity = '0';
      flash.style.transform = 'translateY(-5px)';
      window.setTimeout(() => flash.remove(), 240);
    });
  }, 4200);
})();
