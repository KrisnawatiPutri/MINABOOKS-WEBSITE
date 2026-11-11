(() => {
  'use strict';
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('overlay');
  const menu = document.getElementById('menuToggle');
  const hide = () => { sidebar?.classList.remove('show'); overlay?.classList.remove('show'); };
  menu?.addEventListener('click', () => { sidebar?.classList.toggle('show'); overlay?.classList.toggle('show'); });
  overlay?.addEventListener('click', hide);
  document.addEventListener('keydown', e => { if (e.key === 'Escape') hide(); });
  document.querySelectorAll('[data-table-search]').forEach(input => {
    const table = document.getElementById(input.dataset.tableSearch);
    input.addEventListener('input', () => {
      const keyword = input.value.trim().toLocaleLowerCase('id');
      table?.querySelectorAll('tbody tr').forEach(row => {
        row.hidden = !row.textContent.toLocaleLowerCase('id').includes(keyword);
      });
    });
  });

  // Local canvas drawing with no external chart dependency.
  const chartEl = document.getElementById('performanceChart');
  const chartDataEl = document.getElementById('chart-data');
  if (chartEl && chartDataEl) {
    let chartData;
    try { chartData = JSON.parse(chartDataEl.textContent); } catch { chartData = null; }
    const draw = () => {
      if (!chartData) return;
      const { labels, revenue, costs } = chartData;
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      const rect = chartEl.getBoundingClientRect();
      if (!rect.width) return;
      const width = rect.width, height = rect.height;
      chartEl.width = Math.round(width * ratio);
      chartEl.height = Math.round(height * ratio);
      const ctx = chartEl.getContext('2d');
      ctx.scale(ratio, ratio);
      const left = 60, right = 20, top = 20, bottom = 48;
      const pw = width - left - right, ph = height - top - bottom;
      const max = Math.max(1, ...revenue, ...costs);
      ctx.font = '11px DM Sans, sans-serif';
      ctx.textBaseline = 'middle';
      for (let i=0; i<5; i++) {
        const y = top + ph * i/4;
        ctx.strokeStyle = '#e5edf2'; ctx.lineWidth=1;
        ctx.beginPath(); ctx.moveTo(left,y); ctx.lineTo(width-right,y); ctx.stroke();
        const v = max * (4-i)/4;
        const compact = v >= 1e9 ? `${(v/1e9).toFixed(1)} M` : v >= 1e6 ? `${(v/1e6).toFixed(1)} jt` : v >= 1e3 ? `${(v/1e3).toFixed(0)} rb` : `${v.toFixed(0)}`;
        ctx.fillStyle='#8298a8';ctx.textAlign='right';ctx.fillText(compact,left-9,y);
      }
      const groupW = pw / Math.max(labels.length, 1), barW = Math.min(23,groupW*.25);
      labels.forEach((label,i) => {
        const cx = left + (i+.5)*groupW;
        [revenue[i], costs[i]].forEach((v,j) => {
          const h = Math.max(0,Math.abs(v) / max * ph);
          const x = cx + (j===0 ? -barW-2 : 2);
          ctx.fillStyle=j===0?'#087da0':'#f2ab61';
          ctx.beginPath();
          if (ctx.roundRect) ctx.roundRect(x,top+ph-h,barW,h,[5,5,0,0]);
          else ctx.rect(x,top+ph-h,barW,h);
          ctx.fill();
        });
        ctx.fillStyle='#8298a8';ctx.textAlign='center';ctx.fillText(label,cx,height-21);
      });
    };
    window.addEventListener('resize',draw);
    draw();
  }

  // Django inline formset: add real bound rows with the management counter.
  const form = document.getElementById('journalForm');
  if (form) {
    const totalField = document.getElementById('id_lines-TOTAL_FORMS');
    const rows = document.getElementById('journalRows');
    const template = document.getElementById('journalEmptyRow');
    const currency = value => 'Rp ' + new Intl.NumberFormat('id-ID', {maximumFractionDigits:2}).format(value);
    const recalc = () => {
      let debit = 0, credit = 0;
      rows.querySelectorAll('tr').forEach(row => {
        const removed = row.querySelector('[name$="-DELETE"]')?.checked;
        if (removed) { row.classList.add('row-removed'); return; }
        row.classList.remove('row-removed');
        debit += Number(row.querySelector('[name$="-debit"]')?.value || 0);
        credit += Number(row.querySelector('[name$="-credit"]')?.value || 0);
      });
      document.getElementById('totalDebit').textContent = currency(debit);
      document.getElementById('totalCredit').textContent = currency(credit);
      const difference = document.getElementById('journalDifference');
      difference.textContent = currency(debit-credit);
      difference.classList.toggle('negative',Math.abs(debit-credit)>0.005);
    };
    rows.addEventListener('input',recalc);
    rows.addEventListener('change',recalc);
    document.getElementById('addLine')?.addEventListener('click',() => {
      const index = Number(totalField.value);
      if (index >= 30) { alert('Maksimum 30 baris per jurnal.'); return; }
      rows.insertAdjacentHTML('beforeend',template.innerHTML.replaceAll('__prefix__',String(index)));
      totalField.value = String(index+1);
      recalc();
    });
    recalc();
  }
})();
