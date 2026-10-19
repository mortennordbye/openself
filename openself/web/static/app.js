// OpenSelf web UI: browse, edit and version an OpenSelf profile.
//
//   const ui = OpenSelfUI(container, host);   ui.tick(); ui.search(text);
//
// `host` connects it to a server and a page:
//   get(name, params) -> json     name: profile | state | log | show | asof
//   post(name, body)  -> json     name: save | new | remove | flag | restore   (json.status = HTTP status)
//   status(text, kind)            optional: a status line ('' | 'busy' | 'err')
//   toast(text)                   optional
//   hits(text)                    optional: search result count
//   path(files, root)             optional: the files behind what is shown
//   request(id, text)             optional: ask an assistant about an entry (adds a button)
//   changed()                     optional: called after every write
//   nav                           optional: an element in the host's header to hold the view tabs and
//                                 buttons; without it they are a bar at the top of the container
// The rendered sections carry data-entry, data-section and data-file, so a host can anchor
// comments on selected text.

/* exported OpenSelfUI */
function OpenSelfUI(root, host) {
  'use strict';
  const PF = { data: null, sel: '', view: 'overview', dirty: false, edit: null, filters: { tech: [], removed: false },
               query: '', asof: null, hist: null, conflict: null, loading: false, open: new Set() };
  const store = (() => { try { return window.localStorage; } catch (e) { return null; } })();
  const KEY = 'openself.sel.' + (host.key || 'profile');

  // ---- helpers ------------------------------------------------------------------------------
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
  const ICONS = {
    plus: 'M12 5v14M5 12h14', clock: 'M12 7v5l3 2M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0', note: 'M5 4h14v16H5zM9 9h6M9 13h6M9 17h3',
    chat: 'M4 5h16v11H9l-5 4zM8 9h8M8 12h5', trash: 'M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13', save: 'M5 3h11l4 4v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2zM7 3v6h8V3M7 21v-7h10v7',
    tag: 'M3 12V4h8l10 10-8 8z', help: 'M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.7.4-1 .9-1 1.7M12 17h.01M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0',
    home: 'M3 11l9-7 9 7M5 10v10h14V10M10 20v-6h4v6', timeline: 'M3 6h10M7 12h14M3 18h8', code: 'M8 7l-5 5 5 5M16 7l5 5-5 5',
    briefcase: 'M3 8h18v12H3zM8 8V5h8v3M3 13h18', calendar: 'M4 6h16v15H4zM4 10h16M8 3v4M16 3v4',
    award: 'M12 15a6 6 0 1 0 0-12 6 6 0 0 0 0 12zM8.5 14L7 22l5-3 5 3-1.5-8', pin: 'M12 21s-7-6.3-7-12a7 7 0 0 1 14 0c0 5.7-7 12-7 12zM12 11.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5',
    building: 'M4 21V5l8-3v19M12 9h8v12M8 8h.01M8 12h.01M8 16h.01M16 13h.01M16 17h.01M2 21h20', user: 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 21c0-4 4-6 8-6s8 2 8 6',
    layers: 'M12 3l9 5-9 5-9-5zM3 13l9 5 9-5', info: 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM12 16v-5M12 8h.01', open: 'M7 17L17 7M9 7h8v8',
    chart: 'M4 20V10M10 20V4M16 20v-7M2 20h20', globe: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18',
    git: 'M6 3v12M18 9a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM6 21a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM18 9a9 9 0 0 1-9 9', filter: 'M3 5h18l-7 8v6l-4 2v-8z',
    back: 'M19 12H5M12 19l-7-7 7-7', book: 'M4 4h6a3 3 0 0 1 3 3v14a2 2 0 0 0-2-2H4zM20 4h-6a3 3 0 0 0-3 3v14a2 2 0 0 1 2-2h7z',
  };
  // A label with an icon in front, for rows of facts.
  const withIcon = (n, text, cls) => { const s = el('span', 'os-ic' + (cls ? ' ' + cls : '')); s.append(icon(n), text); return s; };
  const KIND_ICON = { client: 'briefcase', internal: 'building', portfolio: 'layers' };
  const icon = n => { const s = document.createElementNS('http://www.w3.org/2000/svg', 'svg'); s.setAttribute('class', 'os-i'); s.setAttribute('viewBox', '0 0 24 24');
    const p = document.createElementNS('http://www.w3.org/2000/svg', 'path'); p.setAttribute('d', ICONS[n] || ''); s.append(p); return s; };
  const toast = t => host.toast ? host.toast(t) : console.log(t);
  function sanitize(html) {
    const doc = new DOMParser().parseFromString(html, 'text/html');
    doc.querySelectorAll('script,style,iframe,object,embed,link,meta,form,input,button,textarea,select,svg,math').forEach(n => n.remove());
    doc.querySelectorAll('img').forEach(n => n.replaceWith(doc.createTextNode(n.alt || '')));
    doc.querySelectorAll('*').forEach(n => {
      for (const a of [...n.attributes]) { const nm = a.name.toLowerCase(), v = a.value.trim().toLowerCase();
        if (nm.startsWith('on') || nm === 'style' || (nm === 'href' && /^(javascript|data|vbscript):/.test(v))) n.removeAttribute(a.name); }
      if (n.tagName === 'A') { n.target = '_blank'; n.rel = 'noopener noreferrer'; }
    });
    return doc.body.innerHTML;
  }
  const renderMd = text => { const b = el('div', 'os-md'); b.innerHTML = sanitize(marked.parse(text, { gfm: true })); return b; };
  function highlightDom(box, needle, jump) {
    for (const m of box.querySelectorAll('mark.os-hit')) m.replaceWith(document.createTextNode(m.textContent));
    box.normalize(); let first = null;
    if (needle) {
      const w = document.createTreeWalker(box, NodeFilter.SHOW_TEXT), nodes = [];
      while (w.nextNode()) if (!w.currentNode.parentElement.closest('textarea,input')) nodes.push(w.currentNode);
      for (const tn of nodes) {
        const t = tn.nodeValue, low = t.toLowerCase(); if (!low.includes(needle)) continue;
        const frag = document.createDocumentFragment(); let at = 0, i;
        while ((i = low.indexOf(needle, at)) >= 0) { frag.append(t.slice(at, i)); const m = el('mark', 'os-hit', t.slice(i, i + needle.length)); frag.append(m); first = first || m; at = i + needle.length; }
        frag.append(t.slice(at)); tn.replaceWith(frag);
      }
    }
    if (first && jump) first.scrollIntoView({ block: 'center' });
  }

  // ---- words ----------------------------------------------------------------------------------
  const UI = {
    en: { overview: 'Overview', timeline: 'Timeline', tech: 'Technology', questions: 'Questions and gaps', addTech: '+ technology', allKinds: 'all kinds',
      showRemoved: 'show removed', assignment: 'Assignment', employment: 'Employment', history: 'History', newAssignment: 'New assignment',
      newEmployment: 'New employment', asofBanner: 'Showing the profile as it was on {d} (version {r}). Read-only.', backNow: 'Back to now',
      readonly: 'This profile is read-only (readonly in openself.json). Change the original.', editHint: 'Edit, or select text', prevVersion: 'Earlier version',
      roStatus: 'Read-only', noMatch: 'Nothing matches the filter.', withoutEmployment: 'Without employment', removed: 'Removed', choose: 'Choose an entry.',
      period: 'Period', employer: 'Employment', customer: 'Customer', nameable: 'May be named', sector: 'Sector', allocation: 'Allocation', team: 'Team', kind: 'Kind',
      location: 'Location', empType: 'Employment type', breaks: 'Breaks', title: 'Title', languages: 'Languages', clearance: 'Clearance', confidence: 'Confidence',
      reviewed: 'Last reviewed', sources: 'Sources', edit: 'Edit', ask: 'Ask about this', remove: 'Remove', unreadable: 'The file cannot be read: {e}\nEdit it as a raw file to fix it.',
      editRaw: 'Edit raw file', inEmployment: 'Assignments in this employment', noText: 'No text yet. Press Edit.', answer: 'Answer', answerHint: 'Your answer, in your own words. It is stored in quotes after the question.',
      saveAnswer: 'Save answer', cancel: 'Cancel', askMe: 'Ask me about this', answerSaved: 'Answer saved', reloaded: 'The entry changed. Reloading.', couldNot: 'Could not save',
      editing: 'Editing', save: 'Save', form: 'Form', raw: 'Raw file', verified: 'I have checked that everything in this entry is right', verifiedTip: 'Sets confidence to verified',
      discard: 'Discard the changes?', switchView: 'Switching view discards the changes. Continue?', unsaved: 'You have unsaved changes. Discard them?', none: '(none)', notSet: '(not set)',
      number: 'number', ongoingHint: 'YYYY-MM or ongoing', table: 'Table (one row per line)', intro: 'Introduction', flagHint: 'One line per flag: - ⚑ question: …, conflict, emphasis, omit, correction',
      saved: 'Saved and versioned', savedButError: 'Saved, but the file still has an error: {e}', typeEnter: 'type and press Enter', unknownName: 'Not a known name in tech-names.txt',
      conflict: 'This entry was changed elsewhere while you were editing (an assistant, or another tab).', loadTheirs: 'Load their version', keepMine: 'Keep mine',
      keepMineTip: 'Saves your changes over theirs. Their version stays in the history.', whatChanged: 'See what changed', newLead: 'Write in your own words. Save what you have now and fill in the rest later.',
      nameNotPublic: 'How to describe the customer when it may not be named', role: 'Role', from: 'From * (YYYY-MM)', to: 'To (YYYY-MM)', unknownEnd: 'empty = not known',
      ongoing: 'ongoing', allocationPct: 'Allocation (%)', teamSize: 'Team size', technology: 'Technology', toAssistant: 'To the assistant (optional): what should it ask about?',
      saveAndAsk: 'Save and ask me about it', fromFormat: 'From must be YYYY-MM', needEmployer: 'Employer and title are required', needEmployment: 'Create the employment first',
      employerReq: 'Employer *', titleReq: 'Title (exact) *', employmentReq: 'Employment *', mayBeNamed: 'May the customer be named?',
      savedAsk: 'Saved. The assistant will ask you about it.', removeWhy: 'Why remove «{t}»? (stored with the entry; it can be restored from the history)',
      movedRemoved: 'Moved to removed', couldNotRemove: 'Could not remove', askWhat: 'What should the assistant ask about or know? (Empty is fine.)', requested: 'Requested',
      entryHistory: 'History of this entry', noVersions: 'No saved versions yet.', thisChange: 'The change in this version (red removed, green added):',
      restoreHere: 'Restore the entry as it was here', restoreConfirm: 'Restore this version? It becomes a new version; nothing is deleted.', restored: 'Restored',
      showAsOf: 'Show the profile as of this date', noVersion: 'No version found', noDates: 'No dates yet.', gap: 'Ask me about this',
      tlLead: 'The top bar in each row is the employment, the assignments are below. Hatched is a break. Click to open.',
      techLead: 'How long and where each technology was used, from the assignments\' dates. Click one to filter the list.',
      unknownTech: 'Names not in the list of known names (tech-names.txt): ', techHead: ['Technology', 'Months', 'Assignments that show it'],
      qLead: 'What is missing or needs clearing up. Answer here, edit the entry, or ask the assistant. Errors (red) must be fixed, warnings (yellow) are probably mistakes, the rest are gaps.',
      nothing: 'Nothing to clear up.', careerGap: 'Gaps in the career', open: 'Open', entries: '{n} entries', updated: 'Profile updated',
      you: 'you', assistant: 'assistant', tool: 'tool', unknownPeriod: 'unknown period', roleQ: 'role?', titleQ: 'title?', customerQ: 'customer?', portfolio: 'portfolio',
      years: 'y', months: 'mo', openQuestions: '{n} open questions', confidenceUnset: 'confidence not set', untilWord: ' until ', visitAll: 'Show everything with {t}',
      new: 'New', back: 'Overview', aboutJob: 'About the job', aboutMe: 'About me', yearsWorked: 'years working', assignmentsN: 'assignments',
      certsN: 'certifications', topTech: 'Most used technology', allN: 'All {n}', openQ: 'Open questions', answerAll: 'Answer them all',
      noOpenQ: 'No open questions.', showingOnly: 'Showing only', techTip: 'Show only where it was used', certsEdu: 'Certifications and education',
      showRemovedN: 'Show removed ({n})', hideRemoved: 'Hide removed', nowWord: 'now' },
    nb: { overview: 'Oversikt', timeline: 'Tidslinje', tech: 'Teknologi', questions: 'Spørsmål og hull', addTech: '+ teknologi', allKinds: 'alle typer',
      showRemoved: 'vis fjernet', assignment: 'Oppdrag', employment: 'Ansettelse', history: 'Historikk', newAssignment: 'Nytt oppdrag',
      newEmployment: 'Ny ansettelse', asofBanner: 'Viser profilen slik den var {d} (versjon {r}). Skrivebeskyttet.', backNow: 'Tilbake til nå',
      readonly: 'Denne profilen er skrivebeskyttet (readonly i openself.json). Endringer gjøres i originalen.', editHint: 'Rediger, eller marker tekst', prevVersion: 'Tidligere versjon',
      roStatus: 'Skrivebeskyttet', noMatch: 'Ingen oppføringer passer filteret.', withoutEmployment: 'Uten ansettelse', removed: 'Fjernet', choose: 'Velg en oppføring.',
      period: 'Periode', employer: 'Ansettelse', customer: 'Kunde', nameable: 'Kan navngis', sector: 'Bransje', allocation: 'Stilling', team: 'Team', kind: 'Type',
      location: 'Sted', empType: 'Ansettelsesform', breaks: 'Pauser', title: 'Tittel', languages: 'Språk', clearance: 'Klarering', confidence: 'Sikkerhet',
      reviewed: 'Sist sjekket', sources: 'Kilder', edit: 'Rediger', ask: 'Be om intervju', remove: 'Fjern', unreadable: 'Filen kan ikke leses: {e}\nRediger den som rå fil for å rette feilen.',
      editRaw: 'Rediger rå fil', inEmployment: 'Oppdrag i denne ansettelsen', noText: 'Ingen tekst ennå. Trykk Rediger.', answer: 'Svar', answerHint: 'Svaret ditt, med dine ord. Det lagres i anførselstegn etter spørsmålet.',
      saveAnswer: 'Lagre svar', cancel: 'Avbryt', askMe: 'Spør meg om dette', answerSaved: 'Svar lagret', reloaded: 'Oppføringen ble endret. Laster på nytt.', couldNot: 'Kunne ikke lagre',
      editing: 'Redigerer', save: 'Lagre', form: 'Skjema', raw: 'Rå fil', verified: 'Jeg har sjekket at alt i denne oppføringen stemmer', verifiedTip: 'Setter sikkerhet til bekreftet',
      discard: 'Forkaste endringene?', switchView: 'Bytte visning forkaster endringene. Fortsette?', unsaved: 'Du har ulagrede endringer. Forkaste dem?', none: '(ingen)', notSet: '(ikke satt)',
      number: 'tall', ongoingHint: 'YYYY-MM eller ongoing', table: 'Tabell (én rad per linje)', intro: 'Innledning', flagHint: 'Én linje per flagg: - ⚑ spørsmål: …, konflikt, vekt, utelat, retting',
      saved: 'Lagret og versjonert', savedButError: 'Lagret, men filen har fortsatt en feil: {e}', typeEnter: 'skriv og trykk Enter', unknownName: 'Ikke et kjent navn i tech-names.txt',
      conflict: 'Denne oppføringen ble endret et annet sted mens du redigerte (en assistent, eller en annen fane).', loadTheirs: 'Last inn deres versjon', keepMine: 'Behold mine',
      keepMineTip: 'Lagrer dine endringer over deres. Deres versjon finnes fortsatt i historikken.', whatChanged: 'Se hva som ble endret', newLead: 'Skriv med dine egne ord. Lagre det du har nå og fyll ut resten senere.',
      nameNotPublic: 'Omtale når kunden ikke kan navngis', role: 'Rolle', from: 'Fra * (YYYY-MM)', to: 'Til (YYYY-MM)', unknownEnd: 'tom = vet ikke',
      ongoing: 'pågår', allocationPct: 'Stillingsandel (%)', teamSize: 'Teamstørrelse', technology: 'Teknologi', toAssistant: 'Til assistenten (valgfritt): hva vil du fortelle, hva bør den spørre om?',
      saveAndAsk: 'Lagre og be om intervju', fromFormat: 'Fra må være YYYY-MM', needEmployer: 'Arbeidsgiver og tittel må med', needEmployment: 'Lag ansettelsen først',
      employerReq: 'Arbeidsgiver *', titleReq: 'Tittel (nøyaktig) *', employmentReq: 'Ansettelse *', mayBeNamed: 'Kan kunden navngis?',
      savedAsk: 'Lagret. Du blir intervjuet om det.', removeWhy: 'Hvorfor skal «{t}» fjernes? (lagres sammen med oppføringen, den kan hentes tilbake fra historikken)',
      movedRemoved: 'Flyttet til fjernet', couldNotRemove: 'Kunne ikke fjerne', askWhat: 'Hva vil du bli spurt om, eller fortelle? (Tomt er greit.)', requested: 'Bestilt',
      entryHistory: 'Historikk for denne oppføringen', noVersions: 'Ingen lagrede versjoner ennå.', thisChange: 'Endringen i denne versjonen (rødt fjernet, grønt lagt til):',
      restoreHere: 'Gjenopprett oppføringen slik den var her', restoreConfirm: 'Gjenopprette denne versjonen? Det blir en ny versjon, ingenting slettes.', restored: 'Gjenopprettet',
      showAsOf: 'Vis profilen per dato', noVersion: 'Fant ingen versjon', noDates: 'Ingen datoer ennå.', gap: 'Spør meg om dette',
      tlLead: 'Øverste stolpe i hver rad er ansettelsen, under ligger oppdragene. Skravert felt er en pause. Klikk for å åpne.',
      techLead: 'Hvor lenge og hvor du har brukt hver teknologi, regnet fra oppdragenes datoer. Klikk en teknologi for å filtrere lista.',
      unknownTech: 'Navn som ikke står i listen over kjente navn (tech-names.txt): ', techHead: ['Teknologi', 'Måneder', 'Oppdrag som viser det'],
      qLead: 'Det som mangler eller må avklares. Svar her, rediger oppføringen, eller be om intervju. Feil (rødt) må rettes, advarsler (gult) er trolig feil, resten er hull å fylle.',
      nothing: 'Ingenting å avklare.', careerGap: 'Hull i karrieren', open: 'Åpne', entries: '{n} oppføringer', updated: 'Profilen er oppdatert',
      you: 'deg', assistant: 'assistent', tool: 'verktøy', unknownPeriod: 'ukjent periode', roleQ: 'rolle?', titleQ: 'tittel?', customerQ: 'kunde?', portfolio: 'portefølje',
      years: 'år', months: 'mnd', openQuestions: '{n} åpne spørsmål', confidenceUnset: 'sikkerhet ikke satt', untilWord: ' til ', visitAll: 'Vis alt med {t}',
      new: 'Ny', back: 'Oversikt', aboutJob: 'Om jobben', aboutMe: 'Om meg', yearsWorked: 'år i arbeid', assignmentsN: 'oppdrag',
      certsN: 'sertifiseringer', topTech: 'Mest brukt teknologi', allN: 'Alle {n}', openQ: 'Åpne spørsmål', answerAll: 'Svar på alle',
      noOpenQ: 'Ingen åpne spørsmål.', showingOnly: 'Viser bare', techTip: 'Vis bare der den ble brukt', certsEdu: 'Sertifiseringer og utdanning',
      showRemovedN: 'Vis fjernet ({n})', hideRemoved: 'Skjul fjernet', nowWord: 'nå' },
  };
  const t = (k, vars) => { const s = (UI[PF.data && UI[PF.data.lang] ? PF.data.lang : 'en'][k]) ?? UI.en[k] ?? k;
    return typeof s === 'string' && vars ? s.replace(/\{(\w+)\}/g, (_, v) => vars[v]) : s; };
  const ISSUE = { nb: [[/^not given$/, 'ikke oppgitt'], [/^may the customer be named\?$/, 'kan kunden navngis?'],
    [/^how should the customer be described when not named\?$/, 'hvordan omtales kunden når den ikke kan navngis?'], [/^no own contribution written$/, 'eget bidrag er ikke skrevet'],
    [/^needs confirmation from the owner$/, 'må bekreftes av deg'], [/^end is empty; give a month or 'ongoing'$/, 'sluttdato mangler (måned eller pågår)'],
    [/^only the year is known; ask for the month$/, 'bare året er kjent, mangler måned'], [/^not reviewed in over (\d+) months$/, 'ikke sjekket på over $1 måneder'],
    [/^no employment (\S+) to (\S+) \((\d+) months\)$/, 'ingen ansettelse $1 til $2 ($3 måneder)']] };
  const issueText = m => { for (const [re, s] of ISSUE[PF.data.lang] || []) if (re.test(m)) return m.replace(re, s); return m; };

  // ---- data helpers ---------------------------------------------------------------------------
  const L = () => PF.data.labels;
  const fieldLabel = f => L().fields[f] || f;
  const enumLabel = (f, v) => (L().enums[f] || {})[v] || v;
  const sectionLabel = (type, sid) => ((L().sections[type] || {})[sid]) || sid;
  const typeLabel = x => (L().types || {})[x] || x;
  const entries = () => PF.asof ? PF.asof.entries : PF.data.entries;
  const byId = id => entries().find(e => e.id === id);
  const val = (e, k) => { const v = e.meta[k]; return Array.isArray(v) ? v : (v == null ? '' : v); };
  const list = (e, k) => { const v = e.meta[k]; return Array.isArray(v) ? v : (v ? [v] : []); };
  const ym = s => { const m = /^(\d{4})(?:-(\d{2}))?$/.exec(s || ''); return m ? +m[1] * 12 + (m[2] ? +m[2] - 1 : 0) : null; };
  const nowYm = () => { const d = new Date(); return d.getFullYear() * 12 + d.getMonth(); };
  const endYm = e => val(e, 'end') === 'ongoing' ? nowYm() : (ym(val(e, 'end')) ?? ym(val(e, 'start')));
  const period = e => { const s = val(e, 'start'), x = val(e, 'end'); if (!s) return t('unknownPeriod');
    return x === 'ongoing' ? s + ' – ' + fieldLabel('ongoing') : (x && x !== s ? s + ' – ' + x : s); };
  const dur = e => { const a = ym(val(e, 'start')), b = endYm(e); if (a == null || b == null || b < a) return '';
    const n = b - a + 1, y = Math.floor(n / 12), m = n % 12; return (y ? y + ' ' + t('years') : '') + (y && m ? ' ' : '') + (m ? m + ' ' + t('months') : ''); };
  const customerOf = e => {
    if (val(e, 'kind') === 'internal') return enumLabel('kind', 'internal');
    if (val(e, 'kind') === 'portfolio') return list(e, 'customers').length ? list(e, 'customers').join(', ') : (val(e, 'customer_alias') || t('portfolio'));
    return val(e, 'customer') || val(e, 'customer_alias') || val(e, 'sector') || t('customerQ'); };
  const titleOf = e => e.type === 'assignment' ? (val(e, 'role') || t('roleQ')) + ' · ' + customerOf(e)
    : e.type === 'employment' ? (val(e, 'title') || t('titleQ')) + ' · ' + (val(e, 'employer') || '?') : typeLabel(e.type);
  const openFlags = e => e.flags.filter(f => f.open).length;
  const issuesOf = id => (PF.data.issues || []).filter(i => i.id === id);
  const newestFirst = (a, b) => (ym(val(b, 'start')) || 0) - (ym(val(a, 'start')) || 0) || (a.id < b.id ? 1 : -1);
  const status = (s, k) => host.status && host.status(s, k || '');
  const post = async (name, body) => { const j = await host.post(name, body); if (j.ok && host.changed) host.changed(); return j; };

  // ---- loading and live reload ----------------------------------------------------------------
  async function load() {
    PF.loading = true;
    try {
      const d = await host.get('profile');
      if (!d.ok) { root.replaceChildren(el('pre', 'os-err', d.message || 'Could not read the profile')); return; }
      PF.data = d;
      if (!PF.sel || !d.entries.some(e => e.id === PF.sel)) PF.sel = (store && store.getItem(KEY)) || 'person';
      render();
    } finally { PF.loading = false; }
  }
  async function tick() {
    if (!PF.data) { if (!PF.loading) await load(); return; }
    if (PF.loading) return;
    try {
      const s = await host.get('state');
      if (!s.ok || s.version === PF.data.version) return;
      if (!PF.dirty) { await load(); toast(t('updated')); return; }
      const d = await host.get('profile'); if (!d.ok) return;
      const mine = d.entries.find(e => e.id === PF.edit.id), base = PF.data.entries.find(e => e.id === PF.edit.id);
      PF.data = Object.assign(d, { entries: d.entries.map(e => e.id === PF.edit.id && base ? base : e) });
      if (mine && base && mine.sha !== base.sha && !PF.conflict) { PF.conflict = { current_text: mine.text, current_sha: mine.sha }; drawConflict(); }
    } catch (e) { status('', 'err'); }
  }

  // ---- layout ---------------------------------------------------------------------------------
  function render() {
    const old = root.querySelector('.os-main'), keep = old && old.classList.contains('osv-' + PF.view) ? old.firstChild.scrollTop : 0;
    const box = el('div', 'os'), bar = toolbar();
    if (host.nav) host.nav.replaceChildren(bar); else box.append(bar);
    if (PF.asof) {
      const b = el('div', 'os-banner'); b.append(icon('clock'), el('span', '', t('asofBanner', { d: PF.asof.date, r: PF.asof.rev })));
      const back = el('button', 'os-btn', t('backNow')); back.onclick = () => { PF.asof = null; render(); }; b.append(back); box.append(b);
    }
    if (PF.data.readonly) box.append(el('div', 'os-banner', t('readonly')));
    const main = el('div', 'os-main osv-' + PF.view), sc = el('div', 'os-scroll');
    main.append(sc); box.append(main);
    root.replaceChildren(box);
    status(PF.asof ? t('prevVersion') : PF.data.readonly ? t('roStatus') : t('editHint'));
    if (PF.view === 'overview') overview(sc);
    else if (PF.view === 'entry') {
      const page = el('div', 'os-page'), back = el('button', 'os-btn ghost os-back'); back.append(icon('back'), t('back'));
      back.onclick = () => { if (!leaveEdit()) return; const id = PF.sel; PF.view = 'overview'; render(); reveal(id, true); };
      page.append(back, el('section', 'os-detail')); sc.append(page); drawDetail();
    } else {
      const w = el('section', 'os-wide'); sc.append(w);
      if (PF.view === 'timeline') timeline(w); else if (PF.view === 'tech') techView(w); else questions(w);
    }
    sc.scrollTop = keep;
    if (PF.conflict) drawConflict();
  }
  function toolbar() {
    const bar = el('div', 'os-bar' + (host.nav ? ' os-bar-host' : '')), seg = el('span', 'os-seg');
    const nq = PF.data.issues.filter(i => i.level !== 'warning').length;
    for (const [v, label, ic] of [['overview', t('overview'), 'home'], ['timeline', t('timeline'), 'timeline'], ['tech', t('tech'), 'code'], ['questions', t('questions'), 'help']]) {
      const b = el('button', 'os-segb' + (PF.view === v || (v === 'overview' && PF.view === 'entry') ? ' on' : '')); b.append(icon(ic), label);
      if (v === 'questions' && nq) b.append(el('span', 'os-badge', String(nq)));
      b.onclick = () => { if (!leaveEdit()) return; PF.view = v; render(); }; seg.append(b);
    }
    bar.append(seg, el('span', 'os-sp'));
    if (PF.data.history) { const h = el('button', 'os-btn ghost'); h.append(icon('clock'), t('history')); h.onclick = e => { e.stopPropagation(); profileHistory(bar); }; bar.append(h); }
    if (!PF.data.readonly && !PF.asof) {
      const nb = el('button', 'os-btn'); nb.append(icon('plus'), t('new'));
      nb.onclick = e => { e.stopPropagation(); popup(bar, 'os-menu', pop => {
        for (const [type, label] of [['assignment', t('newAssignment')], ['employment', t('newEmployment')]]) {
          const b = el('button'); b.append(icon('plus'), label); b.onclick = () => { pop.remove(); newDialog(type); }; pop.append(b); } }); };
      bar.append(nb);
    }
    return bar;
  }
  // A small panel under the bar; a second click on the same button, or a click outside, closes it.
  function popup(bar, cls, fill) {
    const was = bar.querySelector('.os-pop'); if (was) { was.remove(); if (was.classList.contains(cls)) return null; }
    const pop = el('div', 'os-pop ' + cls); pop.addEventListener('click', ev => ev.stopPropagation()); bar.append(pop); fill(pop);
    setTimeout(() => document.addEventListener('click', function off() { pop.remove(); document.removeEventListener('click', off); }), 0);
    return pop;
  }

  // ---- overview: the career as a stream, newest first -----------------------------------------
  function matches(e) {
    if (e.removed && !PF.filters.removed) return false;
    if (PF.filters.tech.length && !PF.filters.tech.every(x => list(e, 'tech').includes(x))) return false;
    if (PF.query && !(JSON.stringify(e.meta) + ' ' + e.sections.map(s => s.text).join(' ')).toLowerCase().includes(PF.query)) return false;
    return true;
  }
  function overview(box) {
    const all = entries(), live = all.filter(e => !e.removed), shown = new Set(all.filter(matches).map(e => e.id));
    const filtering = !!(PF.query || PF.filters.tech.length), show = e => !filtering || shown.has(e.id);
    const jobs = live.filter(e => e.type === 'employment').sort(newestFirst), jobIds = new Set(jobs.map(j => j.id));
    const kidsOf = j => live.filter(e => e.type === 'assignment' && val(e, 'employment') === j.id).sort(newestFirst);
    const wrap = el('div', 'os-ov'), col = el('div'), side = el('aside', 'os-ov-side');
    wrap.append(col, side); box.append(wrap);
    const p = byId('person');
    if (p) {
      const hero = el('div', 'os-hero'), name = val(p, 'name') || typeLabel('person'), words = name.split(/\s+/).filter(Boolean);
      const av = el('div', 'os-av', words.length > 1 ? words[0][0] + words[words.length - 1][0] : name.slice(0, 2)), info = el('div'), h1 = el('h1'), nb = el('button', '', name);
      nb.onclick = () => select(p.id); h1.append(nb); info.append(h1);
      const line = el('div', 'os-mut os-icrow');
      if (val(p, 'title')) line.append(withIcon('briefcase', val(p, 'title')));
      if (val(p, 'location')) line.append(withIcon('pin', val(p, 'location')));
      for (const u of [val(p, 'github'), val(p, 'linkedin'), ...list(p, 'links')].filter(Boolean)) {
        const a = el('a', 'os-ic'); a.append(icon(/github\.com|gitlab\.com/.test(u) ? 'git' : 'globe'), u.replace(/^https?:\/\/(www\.)?/, '')); a.href = u; a.target = '_blank'; a.rel = 'noopener noreferrer'; line.append(a); }
      info.append(line);
      const about = el('button', 'os-btn'); about.append(icon('user'), t('aboutMe')); about.onclick = () => select(p.id);
      if (openFlags(p)) about.append(el('span', 'os-badge', String(openFlags(p))));
      hero.append(av, info, about); col.append(hero);
    }
    if (PF.filters.tech.length) {
      const f = el('div', 'os-filter'); f.append(icon('filter'), t('showingOnly'));
      for (const x of PF.filters.tech) { const c = el('button', 'os-chip on', x + ' ×'); c.onclick = () => { PF.filters.tech = PF.filters.tech.filter(y => y !== x); render(); }; f.append(c); }
      col.append(f);
    }
    col.append(miniTimeline(jobs, kidsOf, e => !filtering || shown.has(e.id) || kidsOf(e).some(k => shown.has(k.id))));
    const stream = el('div', 'os-stream');
    for (const j of jobs) {
      const kids = kidsOf(j).filter(show);
      if (filtering && !shown.has(j.id) && !kids.length) continue;
      stream.append(node(j, (val(j, 'start') || '?').slice(0, 4), dur(j), val(j, 'end') === 'ongoing' ? 'now' : '', [['building', val(j, 'employer')], ['calendar', period(j)], ['pin', val(j, 'location')]],
        [fold(j, t('aboutJob'), '', '', shown.has(j.id), '', 'info'), ...kids.map(k => fold(k, customerOf(k), val(k, 'role'), period(k), true, '', KIND_ICON[val(k, 'kind')] || 'briefcase'))]));
    }
    const orphans = live.filter(e => e.type === 'assignment' && !jobIds.has(val(e, 'employment'))).filter(show).sort(newestFirst);
    if (orphans.length) stream.append(node(null, '', '', 'plain', [['', t('withoutEmployment')]], orphans.map(k => fold(k, customerOf(k), val(k, 'role'), period(k), true, '', KIND_ICON[val(k, 'kind')] || 'briefcase'))));
    const other = ['certifications', 'education'].map(byId).filter(e => e && !e.removed && show(e));
    if (other.length) stream.append(node(null, '', '', 'plain', [['', t('certsEdu')]], other.map(e => fold(e, typeLabel(e.type), '', '', true, '', e.type === 'education' ? 'book' : 'award'))));
    const removed = all.filter(e => e.removed);
    if (PF.filters.removed && removed.length) stream.append(node(null, '', '', 'plain', [['', t('removed')]], removed.filter(show).map(e => fold(e, e.type === 'employment' ? val(e, 'employer') : customerOf(e), '', val(e, 'removed'), true, 'removed', 'trash'))));
    if (!stream.children.length) stream.append(el('div', 'os-empty', t('noMatch')));
    col.append(stream);
    if (removed.length) { const r = el('button', 'os-link os-ic'); r.append(icon('trash'), PF.filters.removed ? t('hideRemoved') : t('showRemovedN', { n: removed.length })); r.onclick = () => { PF.filters.removed = !PF.filters.removed; render(); }; col.append(r); }
    sideColumn(side, live, jobs);
    if (PF.query) highlightDom(col, PF.query, false);
  }
  // One point on the stream: a year on the left, a card on the right. A card with a job opens it on the title.
  function node(job, year, sub, cls, meta, folds) {
    const n = el('div', 'os-node ' + cls), y = el('div', 'os-yr', year), card = el('div', 'os-card'), top = el('div', 'os-card-top');
    if (sub) y.append(el('small', '', sub));
    if (job) {
      n.dataset.id = job.id; const h = el('button', 'os-card-title', val(job, 'title') || t('titleQ')); h.onclick = () => select(job.id); top.append(h);
      const acts = el('div', 'os-acts'); entryButtons(job, acts, false); top.append(acts);
      const m = el('div', 'os-card-meta os-icrow'); for (const [ic, x] of meta) if (x) m.append(withIcon(ic, x)); card.append(top, m);
    } else { top.append(el('span', 'os-card-title', meta[0][1])); card.append(top); }
    for (const f of folds) card.append(f);
    n.append(y, card); return n;
  }
  // An entry that opens in place. The text is built the first time it opens.
  function fold(e, title, sub, right, hit, cls, ic) {
    const d = el('details', 'os-fold' + (cls ? ' ' + cls : '')), s = el('summary'), tt = el('span', 'os-fold-t'), r = el('span', 'os-fold-r');
    d.dataset.id = e.id; if (ic) tt.append(icon(ic)); tt.append(el('b', '', title)); if (sub) tt.append(' ', el('span', 'os-mut', sub));
    const n = openFlags(e); if (n) { const b = el('span', 'os-badge', String(n)); b.title = t('openQuestions', { n }); r.append(b); }
    if (e.error) r.append(el('span', 'os-badge bad', '!'));
    if (right) r.append(right);
    s.append(tt, r); d.append(s);
    let filled = false;
    const fill = () => { if (filled) return; filled = true; const b = el('div', 'os-fold-in'); entryBody(e, b); if (PF.query) highlightDom(b, PF.query, false); d.append(b); };
    d.open = PF.open.has(e.id) || (!!PF.query && hit && matches(e));
    if (d.open) fill();
    d.addEventListener('toggle', () => { if (d.open) { PF.open.add(e.id); fill(); } else PF.open.delete(e.id); });
    return d;
  }
  function entryBody(e, box) {
    const tech = list(e, 'tech');
    if (tech.length) { const tl = el('div', 'os-tags'); for (const x of tech) { const b = el('button', 'os-chip', x); b.title = t('visitAll', { t: x }); b.onclick = () => { PF.filters.tech = [x]; render(); }; tl.append(b); } box.append(tl); }
    if (e.error) box.append(el('pre', 'os-err', t('unreadable', { e: e.error })));
    for (const s of sectionEls(e)) box.append(s);
    const acts = el('div', 'os-acts'), open = el('button', 'os-btn'); open.append(icon('open'), t('open')); open.onclick = () => select(e.id); acts.append(open);
    entryButtons(e, acts, true); box.append(acts);
  }
  // Edit, history and ask, for an entry shown in the overview. They open it on its own page.
  function entryButtons(e, acts, all) {
    const ro = PF.data.readonly || PF.asof || e.removed;
    const btn = (ic, label, fn) => { const b = el('button', 'os-btn'); b.append(icon(ic), label); b.onclick = ev => { ev.stopPropagation(); fn(); }; acts.append(b); };
    if (!ro) btn('note', t('edit'), () => { if (!select(e.id)) return; PF.edit = { id: e.id }; PF.dirty = false; drawDetail(); });
    if (all && PF.data.history && !PF.asof) btn('clock', t('history'), () => { if (select(e.id)) entryHistory(byId(e.id)); });
    if (all && !ro && host.request) btn('chat', t('ask'), () => request(e.id));
  }
  // Shared by both timelines: year bands, career gaps, the now marker and a hover card.
  function timeFrame(items) {
    const y0 = Math.floor(Math.min(...items.map(e => ym(val(e, 'start')))) / 12), y1 = Math.floor(Math.max(nowYm(), ...items.map(endYm)) / 12), span = (y1 - y0 + 1) * 12;
    return { y0, y1, span, at: mo => (mo - y0 * 12) / span * 100, w: (a, b) => (b - a + 1) / span * 100 };
  }
  function backdrop(f) {
    const bg = el('div', 'os-tlbg');
    for (let y = f.y0; y <= f.y1; y++) if ((y - f.y0) % 2) { const b = el('i', 'os-tlband'); b.style.left = f.at(y * 12) + '%'; b.style.width = f.w(y * 12, y * 12 + 11) + '%'; bg.append(b); }
    for (const g of PF.data.issues.filter(i => i.id === 'employments')) {
      const m = /(\d{4}-\d{2}) to (\d{4}-\d{2}) \((\d+)/.exec(g.message); if (!m) continue;
      const gp = el('i', 'os-tlgap'); gp.style.left = f.at(ym(m[1])) + '%'; gp.style.width = f.w(ym(m[1]), ym(m[2])) + '%'; gp.title = issueText(g.message);
      gp.append(el('span', '', m[3] + ' ' + t('months'))); bg.append(gp);
    }
    const now = el('i', 'os-tlnow'); now.style.left = f.at(nowYm() + 1) + '%'; now.append(el('span', '', t('nowWord'))); bg.append(now);
    return bg;
  }
  function hoverCard(box) {
    const tip = el('div', 'os-tltip'); box.append(tip);
    return (bar, e) => {
      bar.removeAttribute('title');
      bar.addEventListener('mouseenter', () => {
        tip.replaceChildren(el('b', '', e.type === 'assignment' ? customerOf(e) : val(e, 'employer')),
          el('div', '', e.type === 'assignment' ? val(e, 'role') : val(e, 'title')), el('small', '', period(e) + (dur(e) ? ' · ' + dur(e) : '')));
        if (openFlags(e)) tip.append(el('span', 'os-badge', t('openQuestions', { n: openFlags(e) })));
        tip.classList.add('on'); });
      bar.addEventListener('mousemove', ev => { const r = box.getBoundingClientRect(), x = ev.clientX - r.left;
        tip.style.left = Math.min(x + 14, r.width - tip.offsetWidth - 4) + 'px'; tip.style.top = (ev.clientY - r.top + 16) + 'px'; });
      bar.addEventListener('mouseleave', () => tip.classList.remove('on'));
    };
  }
  function miniTimeline(jobs, kidsOf, lit) {
    const box = el('div', 'os-mtl' + (PF.grown ? '' : ' grow')), dated = jobs.filter(j => ym(val(j, 'start')) != null);
    if (!dated.length) return el('div');
    PF.grown = true;
    const f = timeFrame(dated.flatMap(j => [j, ...kidsOf(j)]).filter(e => ym(val(e, 'start')) != null)), card = hoverCard(box);
    const legend = el('div', 'os-mtl-legend');
    for (const [cls, label] of [['job', t('employment')], ['k-client', enumLabel('kind', 'client')], ['k-internal', enumLabel('kind', 'internal')], ['k-portfolio', enumLabel('kind', 'portfolio')]]) {
      const s = el('span'); s.append(el('i', cls), label); legend.append(s); }
    const axis = el('div', 'os-mtl-axis'); for (let y = f.y0; y <= f.y1; y++) { const s = el('span', '', String(y)); s.style.left = f.at(y * 12) + '%'; s.style.width = f.w(0, 11) + '%'; axis.append(s); }
    const lanes = el('div', 'os-mtl-lanes'); lanes.append(backdrop(f));
    const bar = (e, cls, top, n) => { const a = ym(val(e, 'start')), b = endYm(e), d = el('button', 'os-mtl-bar ' + cls + (val(e, 'end') === 'ongoing' ? ' ongoing' : ''));
      d.style.left = f.at(a) + '%'; d.style.width = f.w(a, b) + '%'; if (top != null) d.style.top = top + 'px'; d.style.animationDelay = n * 40 + 'ms';
      card(d, e); d.onclick = () => reveal(e.id, false); return d; };
    let n = 0;
    for (const j of dated) {
      const lane = el('div', 'os-mtl-lane'), jb = bar(j, 'job' + (lit(j) ? '' : ' dim'), null, n++), name = val(j, 'employer'), a = ym(val(j, 'start')), b = endYm(j);
      // The name goes inside the bar when it fits, otherwise beside it, on the side with room.
      if (f.w(a, b) > name.length * 1.1 + 4) jb.append(el('span', '', name));
      else { const lab = el('span', 'os-mtl-lab', name); if (f.at(b + 1) > 70) lab.style.right = 'calc(' + (100 - f.at(a)) + '% + 6px)'; else lab.style.left = 'calc(' + f.at(b + 1) + '% + 6px)'; lane.append(lab); }
      lane.append(jb);
      const rows = [];
      for (const k of kidsOf(j).filter(k => ym(val(k, 'start')) != null).sort((p, q) => ym(val(p, 'start')) - ym(val(q, 'start')))) {
        let r = rows.findIndex(end => end < ym(val(k, 'start'))); if (r < 0) { r = rows.length; rows.push(0); } rows[r] = endYm(k);
        lane.append(bar(k, 'kid k-' + (val(k, 'kind') || 'client') + (lit(k) ? '' : ' dim'), 24 + r * 8, n++));
      }
      lane.style.height = (rows.length ? 28 + rows.length * 8 : 26) + 'px'; lanes.append(lane);
    }
    box.append(legend, axis, lanes); return box;
  }
  function sideColumn(side, live, jobs) {
    const months = new Set(); for (const j of jobs) { const a = ym(val(j, 'start')), b = endYm(j); if (a != null && b != null) for (let m = a; m <= b; m++) months.add(m); }
    const certs = byId('certifications'), rows = certs ? ((certs.sections.find(s => s.id === '_intro') || {}).text || '').split('\n').filter(l => /^\s*\|/.test(l)).length - 2 : 0;
    const stats = el('div', 'os-stats');
    for (const [n, label, ic] of [[(months.size / 12).toFixed(1), t('yearsWorked'), 'calendar'], [live.filter(e => e.type === 'assignment').length, t('assignmentsN'), 'briefcase'], [Math.max(rows, 0), t('certsN'), 'award']]) {
      const d = el('div'); d.append(icon(ic), el('b', '', String(n)), el('span', '', label)); stats.append(d); }
    const sb = el('div', 'os-box'); sb.append(stats); side.append(sb);
    const top = [...PF.data.tech].sort((a, b) => b.months - a.months).slice(0, 12);
    if (top.length) {
      const tb = el('div', 'os-box'), h = el('h3'), all = el('button', 'os-link', t('allN', { n: PF.data.tech.length }));
      h.append(icon('chart'), t('topTech')); all.onclick = () => { PF.view = 'tech'; render(); }; h.append(all); tb.append(h);
      for (const x of top) {
        const r = el('button', 'os-tb' + (PF.filters.tech.includes(x.name) ? ' on' : '')), bar = el('i', x.ongoing ? 'ongoing' : '');
        bar.style.width = x.months / top[0].months * 100 + '%'; r.title = t('techTip');
        r.append(el('span', '', x.name), el('span', '', ''), el('span', '', (x.months / 12).toFixed(1) + ' ' + t('years'))); r.children[1].append(bar);
        r.onclick = () => { PF.filters.tech = PF.filters.tech.includes(x.name) ? [] : [x.name]; render(); }; tb.append(r);
      }
      side.append(tb);
    }
    const qs = live.flatMap(e => e.flags.filter(f => f.open).map(f => [e, f]));
    const qb = el('div', 'os-box'), h = el('h3'); h.append(icon('help'), t('openQ'));
    if (qs.length) h.append(el('span', 'os-badge', String(qs.length)));
    const go = el('button', 'os-link', t('answerAll')); go.onclick = () => { PF.view = 'questions'; render(); }; h.append(go); qb.append(h);
    for (const [e, f] of qs.slice(0, 6)) {
      const b = el('button', 'os-qi'), tx = el('span'); tx.innerHTML = sanitize(marked.parseInline(f.text));
      b.append(el('small', '', e.type === 'assignment' ? customerOf(e) : e.type === 'employment' ? val(e, 'employer') : typeLabel(e.type)), tx);
      b.onclick = () => reveal(e.id, false); qb.append(b);
    }
    if (!qs.length) qb.append(el('div', 'os-mut', t('noOpenQ')));
    side.append(qb);
  }
  // Scroll the overview to an entry and open it; what is not on the stream opens on its own page.
  function reveal(id, quiet) {
    const e = byId(id); if (!e) return;
    const q = x => root.querySelector(x + '[data-id="' + CSS.escape(x === '.os-node' && e.type === 'assignment' ? val(e, 'employment') : id) + '"]');
    const d = e.type === 'employment' ? null : q('.os-fold'), n = d ? d.closest('.os-node') : q('.os-node');
    if (!d && !n) { if (!quiet) select(id); return; }
    if (d) d.open = true;
    (d || n).scrollIntoView({ behavior: quiet ? 'auto' : 'smooth', block: d ? 'center' : 'start' });
    const c = n.querySelector('.os-card'); c.classList.add('flash'); setTimeout(() => c.classList.remove('flash'), 1200);
  }
  function select(id) {
    if (!leaveEdit()) return false;
    PF.sel = id; PF.hist = null; PF.view = 'entry'; if (store) store.setItem(KEY, id);
    render(); return true;
  }
  function leaveEdit() {
    if (!PF.dirty) { PF.edit = null; return true; }
    if (!confirm(t('unsaved'))) return false;
    PF.dirty = false; PF.edit = null; PF.conflict = null; return true;
  }
  window.addEventListener('beforeunload', e => { if (PF.dirty) { e.preventDefault(); e.returnValue = ''; } });

  // ---- detail ---------------------------------------------------------------------------------
  // Icons for the facts on an entry's page, by their label.
  const FACT_ICON = new Proxy({}, { get: (_, k) => ({ period: 'calendar', employer: 'building', customer: 'briefcase', nameable: 'user', sector: 'layers', allocation: 'chart',
    team: 'user', kind: 'tag', location: 'pin', empType: 'briefcase', breaks: 'clock', title: 'briefcase', languages: 'globe', clearance: 'info', confidence: 'info',
    reviewed: 'calendar', sources: 'book', LinkedIn: 'globe', GitHub: 'git' })[Object.keys(UI.en).find(x => t(x) === k) || k] });
  function drawDetail() {
    const box = root.querySelector('.os-detail'); if (!box) return;
    const e = byId(PF.sel); box.replaceChildren();
    if (host.path) host.path(['INDEX.md'].concat(e ? [e.rel] : []), PF.data.path);
    if (!e) { box.append(el('div', 'os-empty', t('choose'))); return; }
    if (PF.edit && PF.edit.id === e.id) { editor(box, e); return; }
    const head = el('div', 'os-head');
    head.append(el('div', 'os-type', typeLabel(e.type) + (e.removed ? ' · ' + t('removed').toLowerCase() + ' ' + val(e, 'removed') : '') + ' · ' + e.id),
      el('h2', '', e.type === 'person' ? (val(e, 'name') || typeLabel('person')) : titleOf(e)));
    const facts = el('div', 'os-facts'), fact = (k, v) => { if (v === '' || v == null) return; const s = el('span', 'os-fact'); s.append(withIcon(FACT_ICON[k] || 'info', k, 'os-fl'), el('span', '', v)); facts.append(s); };
    if (e.type === 'assignment') {
      fact(t('period'), period(e) + (dur(e) ? ' (' + dur(e) + ')' : ''));
      const emp = byId(val(e, 'employment'));
      if (emp) { const s = el('span', 'os-fact'); const a = el('a', '', val(emp, 'employer') + ', ' + val(emp, 'title')); a.href = '#'; a.onclick = ev => { ev.preventDefault(); select(emp.id); }; s.append(withIcon('building', t('employer'), 'os-fl'), a); facts.append(s); }
      fact(t('customer'), val(e, 'kind') === 'portfolio' ? list(e, 'customers').join(', ') : val(e, 'customer'));
      fact(t('nameable'), enumLabel('customer_public', val(e, 'customer_public')) + (val(e, 'customer_public') !== 'public' && val(e, 'customer_alias') ? ': «' + val(e, 'customer_alias') + '»' : ''));
      fact(t('sector'), val(e, 'sector')); fact(t('allocation'), val(e, 'allocation') ? val(e, 'allocation') + ' %' : ''); fact(t('team'), val(e, 'team_size'));
      fact(t('kind'), enumLabel('kind', val(e, 'kind')));
    } else if (e.type === 'employment') {
      fact(t('period'), period(e) + (dur(e) ? ' (' + dur(e) + ')' : '')); fact(t('location'), val(e, 'location'));
      fact(t('empType'), enumLabel('employment_type', val(e, 'employment_type'))); if (list(e, 'breaks').length) fact(t('breaks'), list(e, 'breaks').join(', '));
    } else if (e.type === 'person') {
      fact(t('title'), val(e, 'title')); fact(t('location'), val(e, 'location')); fact(t('languages'), list(e, 'languages').join(', '));
      fact(t('clearance'), val(e, 'clearance') + (val(e, 'clearance_valid_until') ? t('untilWord') + val(e, 'clearance_valid_until') : ''));
      fact('LinkedIn', val(e, 'linkedin')); fact('GitHub', val(e, 'github'));
    }
    fact(t('confidence'), enumLabel('confidence', val(e, 'confidence'))); fact(t('reviewed'), val(e, 'last_reviewed')); fact(t('sources'), list(e, 'sources').join(', '));
    head.append(facts);
    const tech = list(e, 'tech');
    if (tech.length) { const tl = el('div', 'os-tags'); for (const x of tech) { const b = el('button', 'os-chip', x); b.title = t('visitAll', { t: x }); b.onclick = () => { PF.filters.tech = [x]; PF.view = 'overview'; render(); }; tl.append(b); } head.append(tl); }
    const acts = el('div', 'os-acts'), ro = PF.data.readonly || PF.asof || e.removed;
    const btn = (ic, label, fn) => { const b = el('button', 'os-btn'); b.append(icon(ic), label); b.onclick = fn; acts.append(b); };
    if (!ro) btn('note', t('edit'), () => { PF.edit = { id: e.id }; PF.dirty = false; drawDetail(); });
    if (PF.data.history && !PF.asof) btn('clock', t('history'), () => entryHistory(e));
    if (!ro && host.request) btn('chat', t('ask'), () => request(e.id));
    if (!ro && (e.type === 'assignment' || e.type === 'employment')) btn('trash', t('remove'), () => removeEntry(e));
    head.append(acts); box.append(head);
    if (e.error) { box.append(el('pre', 'os-err', t('unreadable', { e: e.error })));
      if (!ro) { const b = el('button', 'os-btn', t('editRaw')); b.onclick = () => { PF.edit = { id: e.id, raw: true }; drawDetail(); }; box.append(b); } }
    const iss = issuesOf(e.id).filter(i => !/^(question|conflict):/.test(i.message));
    if (iss.length) { const ul = el('ul', 'os-issues'); for (const i of iss) ul.append(el('li', 'lv-' + i.level, (i.field ? fieldLabel(i.field) + ': ' : '') + issueText(i.message))); box.append(ul); }
    if (PF.hist && PF.hist.id === e.id) box.append(PF.hist.el);
    for (const s of sectionEls(e)) box.append(s);
    if (e.type === 'employment') {
      const kids = entries().filter(x => x.type === 'assignment' && !x.removed && val(x, 'employment') === e.id).sort(newestFirst);
      if (kids.length) { const sec = el('div', 'os-sec'); sec.append(el('h3', '', t('inEmployment')));
        for (const k of kids) { const a = el('button', 'os-link', customerOf(k) + ' · ' + (val(k, 'role') || '') + ' · ' + period(k)); a.onclick = () => select(k.id); sec.append(a); }
        box.append(sec); }
    }
    if (!e.sections.some(s => s.text.trim()) && !e.error) box.append(el('div', 'os-empty', t('noText')));
    highlightDom(box, PF.query, false);
  }
  function sectionEls(e) {
    const sch = PF.data.schema[e.type] || { sections: [] };
    const rank = s => s.id === '_intro' ? -1 : (sch.sections.indexOf(s.id) < 0 ? 99 : sch.sections.indexOf(s.id));
    return [...e.sections].sort((a, b) => rank(a) - rank(b)).filter(s => s.text.trim()).map(s => {
      const sec = el('div', 'os-sec'); sec.dataset.entry = e.id; sec.dataset.section = s.id; sec.dataset.file = e.file;
      if (s.id !== '_intro') sec.append(el('h3', '', s.known ? sectionLabel(e.type, s.id) : s.heading));
      sec.append(s.id === 'flags' ? flagsView(e, s.text) : renderMd(s.text));
      return sec;
    });
  }
  function flagsView(e, text) {
    const wrap = el('div', 'os-flags');
    for (const f of e.flags) {
      const row = el('div', 'os-flag' + (f.open ? ' open' : '') + (f.resolved ? ' done' : ''));
      row.append(el('span', 'os-ftype t-' + f.type, (L().flags[f.type] || f.type) + (f.resolved ? ' · ' + (L().flags.resolved || 'resolved') + ' ' + f.resolved : '')));
      const tx = el('div', 'os-ftext'); tx.innerHTML = sanitize(marked.parseInline(f.text)); row.append(tx);
      if (f.open && !PF.data.readonly && !PF.asof) {
        const acts = el('div', 'os-acts small'), b = el('button', 'os-btn', t('answer'));
        b.onclick = () => {
          if (row.querySelector('textarea')) return;
          const ta = el('textarea'); ta.placeholder = t('answerHint');
          const go = el('button', 'os-btn on', t('saveAnswer')), cancel = el('button', 'os-btn', t('cancel')), r = el('div', 'os-answer');
          go.onclick = async () => { if (!ta.value.trim()) return; const j = await post('flag', { id: e.id, raw: f.raw, answer: ta.value, base_sha: e.sha });
            if (j.ok) { toast(t('answerSaved')); await load(); } else if (j.status === 409) { toast(t('reloaded')); await load(); } else toast(j.message || t('couldNot')); };
          cancel.onclick = () => r.remove(); r.append(ta, go, cancel); row.append(r); ta.focus();
        };
        acts.append(b);
        if (host.request) { const ask = el('button', 'os-btn ghost', t('askMe')); ask.onclick = () => request(e.id, f.text); acts.append(ask); }
        row.append(acts);
      }
      wrap.append(row);
    }
    const rest = text.split('\n').filter(l => !l.includes('⚑')).join('\n').trim();
    if (rest) wrap.append(renderMd(rest));
    for (const b of e.bad_flags || []) wrap.append(el('div', 'os-flag bad', '⚑? ' + b));
    return wrap;
  }

  // ---- editor ---------------------------------------------------------------------------------
  function grow(ta) { ta.style.height = 'auto'; ta.style.height = Math.min(600, Math.max(70, ta.scrollHeight + 4)) + 'px'; }
  function editor(box, e) {
    const form = el('div', 'os-edit'), sch = PF.data.schema[e.type];
    const save = el('button', 'os-btn on'), dirty = () => { PF.dirty = true; save.disabled = false; };
    form.append(el('div', 'os-type', t('editing') + ' · ' + e.id), el('h2', '', titleOf(e)));
    const bar = el('div', 'os-acts'), cancel = el('button', 'os-btn', t('cancel')), raw = el('button', 'os-btn ghost', PF.edit.raw ? t('form') : t('raw'));
    save.append(icon('save'), t('save')); save.disabled = true; save.title = '⌘S / Ctrl+S';
    const verified = el('label', 'os-check'), vcb = el('input'); vcb.type = 'checkbox'; vcb.onchange = dirty;
    verified.append(vcb, ' ' + t('verified')); verified.title = t('verifiedTip');
    cancel.onclick = () => { if (PF.dirty && !confirm(t('discard'))) return; PF.dirty = false; PF.edit = null; PF.conflict = null; drawDetail(); };
    raw.onclick = () => { if (PF.dirty && !confirm(t('switchView'))) return; PF.dirty = false; PF.edit = { id: e.id, raw: !PF.edit.raw }; drawDetail(); };
    bar.append(save, cancel, raw, verified); form.append(bar, el('div', 'os-conflict-slot'));
    let collect;
    const skip = new Set(['schema', 'id', 'type', 'status', 'removed', 'removed_reason', 'last_reviewed']);
    if (PF.edit.raw) {
      const ta = el('textarea', 'os-raw'); ta.value = e.text; ta.oninput = dirty; form.append(ta);
      collect = () => ({ text: ta.value });
    } else {
      const grid = el('div', 'os-grid'), inputs = {};
      for (const f of sch.fields) {
        if (skip.has(f.name) || (!f.scaffold && !(f.name in e.meta))) continue;
        if (e.type === 'assignment' && f.name === 'customers' && val(e, 'kind') !== 'portfolio' && !list(e, 'customers').length) continue;
        const lab = el('label', 'os-field' + (f.type === 'array' ? ' wide' : '')); lab.append(el('span', '', fieldLabel(f.name) + (sch.required.includes(f.name) ? ' *' : ''))); lab.title = f.description;
        let inp;
        if (f.name === 'employment') {
          inp = el('select', 'os-select'); const o0 = el('option', '', t('none')); o0.value = ''; inp.append(o0);
          for (const j of PF.data.entries.filter(x => x.type === 'employment' && !x.removed).sort(newestFirst)) { const o = el('option', '', val(j, 'employer') + ', ' + val(j, 'title') + ' (' + period(j) + ')'); o.value = j.id; inp.append(o); }
          inp.value = val(e, f.name);
        } else if (f.enum && f.type !== 'array') {
          inp = el('select', 'os-select'); for (const v of f.enum) { const o = el('option', '', v ? enumLabel(f.name, v) : t('notSet')); o.value = v; inp.append(o); } inp.value = val(e, f.name);
        } else if (f.type === 'array') {
          inp = tagInput(list(e, f.name), f.name === 'tech' ? PF.data.tech_names : null, dirty);
        } else {
          inp = el('input'); inp.value = val(e, f.name);
          if (f.integer) { inp.inputMode = 'numeric'; inp.placeholder = t('number'); }
          if (f.name === 'start') inp.placeholder = 'YYYY-MM'; if (f.name === 'end') inp.placeholder = t('ongoingHint');
          if (/_until$/.test(f.name)) inp.placeholder = 'YYYY-MM-DD';
        }
        if (inp.tagName !== 'DIV') inp.oninput = inp.onchange = dirty;
        lab.append(inp); grid.append(lab); inputs[f.name] = inp;
        if (f.name === 'end') { const og = el('label', 'os-check'), cb = el('input'); cb.type = 'checkbox'; cb.checked = inp.value === 'ongoing';
          cb.onchange = () => { inp.value = cb.checked ? 'ongoing' : ''; dirty(); }; og.append(cb, ' ' + fieldLabel('ongoing')); lab.append(og); }
      }
      form.append(grid);
      const secs = {}, present = new Map(e.sections.map(s => [s.id, s]));
      const ids = [...(sch.table ? ['_intro'] : []), ...sch.sections, ...e.sections.filter(s => !s.known && s.id !== '_intro').map(s => s.id)];
      if (present.has('_intro') && !ids.includes('_intro')) ids.unshift('_intro');
      for (const sid of ids) {
        const s = present.get(sid), lab = el('label', 'os-field wide os-secedit');
        lab.append(el('span', '', sid === '_intro' ? (sch.table ? t('table') : t('intro')) : s && !s.known ? s.heading : sectionLabel(e.type, sid)));
        if (sid === 'flags') lab.append(el('small', '', t('flagHint')));
        const ta = el('textarea'); ta.value = s ? s.text : ''; ta.oninput = () => { dirty(); grow(ta); };
        lab.append(ta); form.append(lab); secs[sid] = { ta, heading: s ? s.heading : '' }; requestAnimationFrame(() => grow(ta));
      }
      collect = () => {
        const meta = {};
        for (const [k, inp] of Object.entries(inputs)) meta[k] = inp.getValues ? inp.getValues() : inp.value.trim();
        for (const k of Object.keys(e.meta)) if (!(k in meta) && !skip.has(k)) meta[k] = e.meta[k];
        for (const k of ['status', 'removed', 'removed_reason']) if (k in e.meta) meta[k] = e.meta[k];
        return { meta, sections: Object.entries(secs).map(([id, s]) => ({ id, heading: s.heading, text: s.ta.value })) };
      };
    }
    const doSave = async base => {
      if (!PF.dirty && !base) return;
      save.disabled = true;
      const j = await post('save', Object.assign({ id: e.id, base_sha: base || e.sha, verified: vcb.checked }, collect()));
      if (j.ok) { PF.dirty = false; PF.edit = null; PF.conflict = null; toast(j.error ? t('savedButError', { e: j.error }) : t('saved')); await load(); return; }
      save.disabled = false;
      if (j.status === 409) { PF.conflict = { current_text: j.current_text, current_sha: j.current_sha }; drawConflict(); } else toast(j.message || t('couldNot'));
    };
    save.onclick = () => doSave(); PF.edit.save = doSave;
    box.append(form);
    if (PF.conflict) drawConflict();
  }
  function tagInput(values, suggestions, onChange) {
    const box = el('div', 'os-tagin'), inp = el('input'); let vals = [...values];
    const known = suggestions ? new Set(suggestions.map(s => s.toLowerCase())) : null;
    if (suggestions) { const dl = el('datalist'); dl.id = 'osdl' + Math.random().toString(36).slice(2); for (const s of suggestions) { const o = el('option'); o.value = s; dl.append(o); } box.append(dl); inp.setAttribute('list', dl.id); }
    const draw = () => { box.querySelectorAll('.os-chip').forEach(c => c.remove());
      for (const v of vals) { const bad = known && !known.has(v.toLowerCase()), c = el('button', 'os-chip' + (bad ? ' warn' : ''), v + ' ×'); c.type = 'button';
        if (bad) c.title = t('unknownName'); c.onclick = () => { vals = vals.filter(x => x !== v); draw(); onChange(); }; box.insertBefore(c, inp); } };
    const add = () => { for (const v of inp.value.split(',').map(s => s.trim()).filter(Boolean)) if (!vals.includes(v)) vals.push(v); inp.value = ''; draw(); onChange(); };
    inp.placeholder = t('typeEnter');
    inp.onkeydown = ev => { if (ev.key === 'Enter' || ev.key === ',') { ev.preventDefault(); add(); } else if (ev.key === 'Backspace' && !inp.value && vals.length) { vals.pop(); draw(); onChange(); } };
    inp.onchange = () => { if (suggestions && suggestions.includes(inp.value)) add(); }; inp.onblur = () => { if (inp.value.trim()) add(); };
    box.append(inp); draw(); box.getValues = () => { if (inp.value.trim()) add(); return vals; };
    return box;
  }
  function drawConflict() {
    const slot = root.querySelector('.os-conflict-slot') || root.querySelector('.os-detail'); if (!slot || !PF.conflict) return;
    slot.querySelector('.os-conflict')?.remove();
    const e = byId(PF.edit ? PF.edit.id : PF.sel), box = el('div', 'os-conflict'), row = el('div', 'os-acts');
    box.append(el('b', '', t('conflict')));
    const theirs = el('button', 'os-btn', t('loadTheirs')); theirs.onclick = async () => { PF.dirty = false; PF.edit = null; PF.conflict = null; await load(); };
    const mine = el('button', 'os-btn', t('keepMine')); mine.title = t('keepMineTip');
    mine.onclick = () => { const c = PF.conflict; PF.conflict = null; box.remove(); PF.dirty = true; if (PF.edit && PF.edit.save) PF.edit.save(c.current_sha); };
    const diff = el('button', 'os-btn ghost', t('whatChanged')); diff.onclick = () => { if (!box.querySelector('.os-diff')) box.append(diffView(e ? e.text : '', PF.conflict.current_text || '')); };
    row.append(theirs, mine, diff); box.append(row); slot.prepend(box);
  }

  // ---- new, remove, request -------------------------------------------------------------------
  function newDialog(type) {
    let d = document.getElementById('osnew'); if (d) d.remove();
    d = el('dialog', 'os-dialog'); d.id = 'osnew'; document.body.append(d);
    d.append(el('h2', '', type === 'assignment' ? t('newAssignment') : t('newEmployment')), el('p', 'os-lead', t('newLead')));
    const grid = el('div', 'os-grid'), inputs = {};
    const field = (name, label, make) => { const lab = el('label', 'os-field'); lab.append(el('span', '', label)); const inp = make ? make() : el('input'); lab.append(inp); grid.append(lab); inputs[name] = inp; return inp; };
    const sel = opts => () => { const s = el('select', 'os-select'); for (const [v, l] of opts) { const o = el('option', '', l); o.value = v; s.append(o); } return s; };
    if (type === 'assignment') {
      field('kind', fieldLabel('kind'), sel([['client', enumLabel('kind', 'client')], ['portfolio', enumLabel('kind', 'portfolio')], ['internal', enumLabel('kind', 'internal')]]));
      field('employment', t('employmentReq'), sel(PF.data.entries.filter(x => x.type === 'employment' && !x.removed).sort(newestFirst).map(j => [j.id, val(j, 'employer') + ', ' + val(j, 'title')])));
      field('customer', t('customer'));
      field('customer_public', t('mayBeNamed'), sel(['unknown', 'public', 'anonymised', 'nda'].map(v => [v, enumLabel('customer_public', v)])));
      field('customer_alias', t('nameNotPublic')); field('role', t('role'));
    } else {
      field('employer', t('employerReq')); field('title', t('titleReq')); field('location', t('location'));
      field('employment_type', t('empType'), sel(PF.data.schema.employment.fields.find(f => f.name === 'employment_type').enum.map(v => [v, v ? enumLabel('employment_type', v) : t('notSet')])));
    }
    field('start', t('from')).placeholder = '2026-01'; const end = field('end', t('to')); end.placeholder = t('unknownEnd');
    const og = el('label', 'os-check'), ocb = el('input'); ocb.type = 'checkbox'; ocb.onchange = () => { end.value = ocb.checked ? 'ongoing' : ''; end.disabled = ocb.checked; };
    og.append(ocb, ' ' + t('ongoing')); end.parentElement.append(og);
    if (type === 'assignment') { field('allocation', t('allocationPct')).inputMode = 'numeric'; field('team_size', t('teamSize')).inputMode = 'numeric'; }
    const tl = el('label', 'os-field wide'); tl.append(el('span', '', t('technology'))); const tech = tagInput([], PF.data.tech_names, () => {}); tl.append(tech); grid.append(tl);
    d.append(grid);
    const texts = {};
    for (const sid of type === 'assignment' ? ['summary', 'contribution', 'outcome'] : ['summary']) {
      const lab = el('label', 'os-field wide'); lab.append(el('span', '', sectionLabel(type, sid))); const ta = el('textarea'); ta.rows = 3; lab.append(ta); d.append(lab); texts[sid] = ta;
    }
    let askTa = null;
    if (host.request) { const ask = el('label', 'os-field wide'); ask.append(el('span', '', t('toAssistant'))); askTa = el('textarea'); askTa.rows = 2; ask.append(askTa); d.append(ask); }
    const row = el('div', 'os-acts end'), msg = el('span', 'os-msg'), cancel = el('button', 'os-btn', t('cancel')), saveB = el('button', 'os-btn on', t('save'));
    row.append(msg, cancel); let interview = null;
    if (host.request) { interview = el('button', 'os-btn', t('saveAndAsk')); row.append(interview); }
    row.append(saveB); d.append(row);
    cancel.onclick = () => d.close();
    const submit = async alsoAsk => {
      const fields = {}; for (const [k, inp] of Object.entries(inputs)) fields[k] = inp.value.trim(); fields.tech = tech.getValues();
      if (!/^\d{4}(-\d{2})?$/.test(fields.start)) { msg.textContent = t('fromFormat'); return; }
      if (type === 'employment' && (!fields.employer || !fields.title)) { msg.textContent = t('needEmployer'); return; }
      if (type === 'assignment' && !fields.employment) { msg.textContent = t('needEmployment'); return; }
      if (alsoAsk) fields.confidence = 'needs-confirmation';
      const secs = {}; for (const [k, ta] of Object.entries(texts)) if (ta.value.trim()) secs[k] = ta.value;
      saveB.disabled = true;
      const j = await post('new', { type, fields, sections: secs }); saveB.disabled = false;
      if (!j.ok) { msg.textContent = j.message || t('couldNot'); return; }
      if (alsoAsk) await host.request(j.id, askTa.value.trim());
      d.close(); PF.sel = j.id; PF.view = 'entry'; await load(); toast(alsoAsk ? t('savedAsk') : t('saved'));
    };
    saveB.onclick = () => submit(false); if (interview) interview.onclick = () => submit(true);
    d.showModal(); (inputs.customer || inputs.employer).focus();
  }
  async function removeEntry(e) {
    const reason = prompt(t('removeWhy', { t: titleOf(e) }), ''); if (!reason || !reason.trim()) return;
    const j = await post('remove', { id: e.id, reason, base_sha: e.sha });
    toast(j.ok ? t('movedRemoved') : j.message || t('couldNotRemove')); if (j.ok) await load();
  }
  async function request(id, quote) {
    const c = prompt(t('askWhat'), ''); if (c === null) return;
    const j = await host.request(id, c, quote || ''); toast((j && j.message) || t('requested'));
  }

  // ---- history, diff and as-of ----------------------------------------------------------------
  const when = s => new Date(s).toLocaleString(PF.data.lang === 'nb' ? 'nb-NO' : undefined, { dateStyle: 'medium', timeStyle: 'short' });
  const actorName = a => ({ owner: t('you'), claude: t('assistant'), tool: t('tool') }[a] || a || '');
  function revRow(it, cls) {
    const r = el(cls === 'button' ? 'button' : 'div', 'os-rev'), top = el('div', 'os-revtop');
    top.append(el('code', '', it.short), el('span', '', actorName(it.actor)));
    for (const x of it.tags || []) { const g = el('span', 'os-tag'); g.append(icon('tag'), x); top.append(g); }
    top.append(el('span', 'os-when', when(it.date))); r.append(top, el('div', 'os-sub', it.subject.replace(/ \[\w+\]$/, '')));
    return r;
  }
  async function entryHistory(e) {
    if (PF.hist && PF.hist.id === e.id) { PF.hist = null; drawDetail(); return; }
    const box = el('div', 'os-hist'); box.append(el('h3', '', t('entryHistory')));
    PF.hist = { id: e.id, el: box }; drawDetail();
    const j = await host.get('log', { id: e.id });
    if (!j.ok || !j.items.length) { box.append(el('div', 'os-empty', t('noVersions'))); return; }
    const out = el('div');
    j.items.forEach((it, n) => {
      const b = revRow(it, 'button');
      b.onclick = async () => {
        box.querySelectorAll('.os-rev').forEach(x => x.classList.toggle('on', x === b));
        const cur = await host.get('show', { id: e.id, rev: it.rev });
        const prev = j.items[n + 1] ? await host.get('show', { id: e.id, rev: j.items[n + 1].rev }) : { text: '' };
        out.replaceChildren(el('div', 'os-lead', t('thisChange')), diffView(prev.text || '', cur.text || ''));
        if (n > 0 && !PF.data.readonly) { const r = el('button', 'os-btn', t('restoreHere')); r.onclick = async () => {
          if (!confirm(t('restoreConfirm'))) return;
          const res = await post('restore', { id: e.id, rev: it.rev }); toast(res.ok ? t('restored') : res.message || t('couldNot')); if (res.ok) { PF.hist = null; await load(); } };
          out.append(r); }
      };
      box.append(b);
    });
    box.append(out);
  }
  async function profileHistory(bar) {
    const pop = popup(bar, 'os-hpop', () => {}); if (!pop) return;
    const dRow = el('div', 'os-asof'), di = el('input'); di.type = 'date'; di.value = new Date().toISOString().slice(0, 10);
    const go = el('button', 'os-btn', t('showAsOf'));
    go.onclick = async () => { const j = await host.get('asof', { date: di.value }); if (!j.ok) { toast(j.message || t('noVersion')); return; }
      if (!leaveEdit()) return; PF.asof = { date: di.value, rev: j.rev, entries: j.entries }; pop.remove(); PF.view = 'overview'; render(); };
    dRow.append(di, go); pop.append(dRow);
    const j = await host.get('log');
    for (const it of (j.items || []).slice(0, 80)) pop.append(revRow(it));
  }
  function diffView(a, b) { const box = el('div', 'os-diff'); for (const [op, x] of wordDiff(a, b)) box.append(op === '=' ? document.createTextNode(x) : el(op === '+' ? 'ins' : 'del', '', x)); return box; }
  function wordDiff(a, b) {
    const tok = s => s.match(/\s+|[\p{L}\p{N}_]+|[^\s\p{L}\p{N}_]/gu) || [];
    const x = tok(a), y = tok(b), n = x.length, m = y.length;
    if (n * m > 6e6) return [['-', a], ['+', b]];
    const w = m + 1, dp = new Uint32Array((n + 1) * w);
    for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) dp[i * w + j] = x[i] === y[j] ? dp[(i + 1) * w + j + 1] + 1 : Math.max(dp[(i + 1) * w + j], dp[i * w + j + 1]);
    const out = [], push = (op, s) => { if (out.length && out[out.length - 1][0] === op) out[out.length - 1][1] += s; else out.push([op, s]); };
    let i = 0, j = 0;
    while (i < n && j < m) { if (x[i] === y[j]) { push('=', x[i]); i++; j++; } else if (dp[(i + 1) * w + j] >= dp[i * w + j + 1]) push('-', x[i++]); else push('+', y[j++]); }
    while (i < n) push('-', x[i++]); while (j < m) push('+', y[j++]);
    return out;
  }

  // ---- timeline, technology, questions --------------------------------------------------------
  function timeline(box) {
    const all = entries().filter(e => !e.removed && (e.type === 'employment' || e.type === 'assignment') && ym(val(e, 'start')) != null);
    if (!all.length) { box.append(el('div', 'os-empty', t('noDates'))); return; }
    const f = timeFrame(all), pct = mo => f.at(mo) + '%', wid = (a, b) => f.w(a, b) + '%';
    const tl = el('div', 'os-tl'), axis = el('div', 'os-tl-axis'), rows = el('div', 'os-tl-rows'), card = hoverCard(tl);
    for (let y = f.y0; y <= f.y1; y++) { const s = el('span', '', String(y)); s.style.left = pct(y * 12); s.style.width = wid(0, 11); axis.append(s); }
    tl.append(axis); rows.append(backdrop(f));
    for (const g of PF.data.issues.filter(i => i.id === 'employments')) {
      const r = el('div', 'os-gapnote'); r.append(icon('help'), el('span', '', issueText(g.message).replace(/^./, c => c.toUpperCase())));
      if (host.request) { const b = el('button', 'os-btn ghost', t('gap')); b.onclick = () => request('', g.message); r.append(b); }
      tl.append(r);
    }
    const bar = (e, cls) => {
      const a = ym(val(e, 'start')), b = endYm(e), d = el('button', 'os-tl-bar ' + cls + (val(e, 'end') === 'ongoing' ? ' ongoing' : ''));
      d.style.left = pct(a); d.style.width = wid(a, b);
      d.append(el('span', '', e.type === 'assignment' ? customerOf(e) : val(e, 'employer') + ', ' + val(e, 'title')));
      for (const br of list(e, 'breaks')) { const [p, q] = br.split('/'), bx = ym(p), by = ym(q); if (bx == null || by == null) continue;
        const h = el('i', 'os-tl-break'); h.style.left = ((bx - a) / (b - a + 1) * 100) + '%'; h.style.width = ((by - bx + 1) / (b - a + 1) * 100) + '%'; h.title = br; d.append(h); }
      card(d, e); d.onclick = () => select(e.id); return d;
    };
    for (const j of all.filter(e => e.type === 'employment').sort(newestFirst)) {
      const row = el('div', 'os-tl-row'); row.append(bar(j, 'job'));
      const lanes = [];
      for (const k of all.filter(e => e.type === 'assignment' && val(e, 'employment') === j.id).sort((p, q) => ym(val(p, 'start')) - ym(val(q, 'start')))) {
        let li = lanes.findIndex(end => end < ym(val(k, 'start'))); if (li < 0) { lanes.push(0); li = lanes.length - 1; } lanes[li] = endYm(k);
        const b = bar(k, 'kid k-' + (val(k, 'kind') || 'client')); b.style.top = (26 + li * 22) + 'px'; row.append(b);
      }
      row.style.height = (30 + lanes.length * 22) + 'px'; rows.append(row);
    }
    tl.append(rows); box.append(tl, el('div', 'os-lead', t('tlLead')));
  }
  function techView(box) {
    const tb = el('table', 'os-table'), hr = el('tr'); for (const h of t('techHead')) hr.append(el('th', '', h)); tb.append(hr);
    for (const r of PF.data.tech) {
      const tr = el('tr'), name = el('td'), b = el('button', 'os-chip', r.name); b.onclick = () => { PF.filters.tech = [r.name]; PF.view = 'overview'; render(); }; name.append(b);
      const ids = el('td'); for (const id of r.ids) { const e = byId(id), a = el('button', 'os-link inline', e ? customerOf(e) + ' (' + (val(e, 'start') || '?').slice(0, 4) + ')' : id); a.onclick = () => select(id); ids.append(a); }
      tr.append(name, el('td', '', r.months + (r.ongoing ? '+' : '')), ids); tb.append(tr);
    }
    const unknown = new Set(); for (const e of entries()) for (const x of list(e, 'tech')) if (!PF.data.tech_names.includes(x)) unknown.add(x);
    box.append(el('p', 'os-lead', t('techLead')), tb);
    if (unknown.size) box.append(el('p', 'os-lead', t('unknownTech') + [...unknown].join(', ')));
  }
  function questions(box) {
    const groups = new Map();
    for (const i of PF.data.issues) { if (!groups.has(i.id)) groups.set(i.id, []); groups.get(i.id).push(i); }
    box.append(el('p', 'os-lead', t('qLead')));
    if (!groups.size) { box.append(el('div', 'os-empty', t('nothing'))); return; }
    const order = id => { const e = byId(id); return e ? ['person', 'certifications', 'education'].indexOf(e.type) + 10 * (e.type === 'assignment') : -1; };
    for (const [id, items] of [...groups.entries()].sort((a, b) => order(a[0]) - order(b[0]))) {
      const e = byId(id), card = el('div', 'os-qcard'), head = el('div', 'os-qhead');
      head.append(el('b', '', e ? titleOf(e) : id === 'employments' ? t('careerGap') : id));
      if (e) { const o = el('button', 'os-btn ghost'); o.append(icon('open'), t('open')); o.onclick = () => select(e.id); head.append(o);
        if (!PF.data.readonly && host.request) { const a = el('button', 'os-btn ghost', t('ask')); a.onclick = () => request(e.id, items.map(i => i.message).join('; ')); head.append(a); } }
      card.append(head);
      for (const i of items) {
        const flag = e && e.flags.find(f => f.open && i.message === f.type + ': ' + f.text);
        if (flag) card.append(flagsView(Object.assign({}, e, { flags: [flag], bad_flags: [] }), ''));
        else card.append(el('div', 'os-q lv-' + i.level, (i.field ? fieldLabel(i.field) + ': ' : '') + issueText(i.message)));
      }
      box.append(card);
    }
  }

  // ---- search and keys --------------------------------------------------------------------------
  function search(needle, jump) {
    if (!PF.data) return;
    PF.query = (needle || '').trim().toLowerCase();
    if (PF.view === 'entry') { const d = root.querySelector('.os-detail'); if (d && !PF.edit) highlightDom(d, PF.query, jump); }
    else { PF.view = 'overview'; render(); if (jump) root.querySelector('mark.os-hit')?.scrollIntoView({ block: 'center' }); }
    if (host.hits) host.hits(PF.query ? t('entries', { n: entries().filter(matches).length }) : '');
  }
  const onKey = e => { if ((e.metaKey || e.ctrlKey) && e.key === 's' && PF.edit && PF.edit.save && root.isConnected) { e.preventDefault(); PF.edit.save(); } };
  document.addEventListener('keydown', onKey);

  return { tick, search, reload: load, dirty: () => PF.dirty, destroy: () => { document.removeEventListener('keydown', onKey); if (host.nav) host.nav.replaceChildren(); } };
}
