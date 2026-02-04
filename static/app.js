const form = document.getElementById('scan-form');
const rootInput = document.getElementById('root');
const statusEl = document.getElementById('status');
const repoContainer = document.getElementById('repo-container');
const tooltip = document.getElementById('tooltip');

const defaultRoot = '';
rootInput.value = defaultRoot;

const formatParents = (parents) => (parents && parents.length ? parents.join(', ') : 'ندارد');

const showStatus = (message, tone = 'info') => {
  statusEl.textContent = message;
  statusEl.className = `status ${tone}`;
};

const hideTooltip = () => {
  tooltip.setAttribute('aria-hidden', 'true');
  tooltip.style.opacity = 0;
};

const showTooltip = (event, data) => {
  tooltip.innerHTML = `
    <div class="tooltip-title">${data.short}</div>
    <div class="tooltip-row"><span>پیام:</span> <strong>${data.message || '-'}</strong></div>
    <div class="tooltip-row"><span>نویسنده:</span> ${data.author || '-'}</div>
    <div class="tooltip-row"><span>تاریخ:</span> ${data.date || '-'}</div>
    <div class="tooltip-row"><span>والدها:</span> ${formatParents(data.parents)}</div>
  `;
  tooltip.setAttribute('aria-hidden', 'false');
  tooltip.style.opacity = 1;
  moveTooltip(event);
};

const moveTooltip = (event) => {
  const offset = 16;
  tooltip.style.left = `${event.pageX + offset}px`;
  tooltip.style.top = `${event.pageY + offset}px`;
};

const renderRepo = (repo) => {
  const section = document.createElement('section');
  section.className = 'repo-card';

  const header = document.createElement('div');
  header.className = 'repo-header';
  header.innerHTML = `
    <div>
      <h2>${repo.name}</h2>
      <p>${repo.path}</p>
    </div>
    <div class="commit-count">${repo.commit_count} کامیت</div>
  `;

  const body = document.createElement('div');
  body.className = 'repo-body';

  if (!repo.tree) {
    body.innerHTML = '<p class="empty">هیچ تاریخچه‌ای برای نمایش وجود ندارد.</p>';
    section.append(header, body);
    return section;
  }

  const svg = d3.create('svg');
  const width = 1000;
  const margin = { top: 40, right: 140, bottom: 40, left: 140 };

  const root = d3.hierarchy(repo.tree);
  const treeLayout = d3.tree().nodeSize([48, 200]);
  treeLayout(root);

  let x0 = Infinity;
  let x1 = -x0;
  root.each((d) => {
    if (d.x > x1) x1 = d.x;
    if (d.x < x0) x0 = d.x;
  });

  const height = x1 - x0 + margin.top + margin.bottom;
  svg.attr('viewBox', [0, 0, width, height]);

  const g = svg.append('g').attr('transform', `translate(${margin.left},${margin.top - x0})`);

  const linkGenerator = d3.linkHorizontal().x((d) => d.y).y((d) => d.x);

  g.append('g')
    .attr('class', 'links')
    .selectAll('path')
    .data(root.links())
    .join('path')
    .attr('class', 'link')
    .attr('d', linkGenerator);

  if (repo.merge_links && repo.merge_links.length) {
    const nodeById = new Map();
    root.each((d) => nodeById.set(d.data.id, d));
    const mergePaths = repo.merge_links
      .map((link) => ({
        source: nodeById.get(link.source),
        target: nodeById.get(link.target),
      }))
      .filter((link) => link.source && link.target);

    g.append('g')
      .attr('class', 'links merge')
      .selectAll('path')
      .data(mergePaths)
      .join('path')
      .attr('class', 'link merge')
      .attr('d', (d) =>
        linkGenerator({
          source: { x: d.source.x, y: d.source.y },
          target: { x: d.target.x, y: d.target.y },
        })
      );
  }

  const node = g
    .append('g')
    .attr('class', 'nodes')
    .selectAll('g')
    .data(root.descendants())
    .join('g')
    .attr('class', 'node')
    .attr('transform', (d) => `translate(${d.y},${d.x})`)
    .on('mouseenter', (event, d) => showTooltip(event, d.data))
    .on('mousemove', moveTooltip)
    .on('mouseleave', hideTooltip);

  node
    .append('circle')
    .attr('r', 14)
    .attr('class', 'node-circle');

  node
    .append('text')
    .attr('class', 'node-label')
    .attr('x', 22)
    .attr('dy', '0.35em')
    .text((d) => d.data.short);

  body.appendChild(svg.node());
  section.append(header, body);
  return section;
};

const render = async (root) => {
  repoContainer.innerHTML = '';
  hideTooltip();
  showStatus('در حال اسکن پوشه‌ها ...', 'info');
  const params = new URLSearchParams();
  if (root) {
    params.set('root', root);
  }
  try {
    const response = await fetch(`/api/repos?${params.toString()}`);
    const payload = await response.json();
    if (!response.ok) {
      showStatus(payload.error || 'خطا در دریافت اطلاعات.', 'error');
      return;
    }
    if (!payload.repos.length) {
      showStatus('ریپوی گیتی پیدا نشد.', 'warning');
      return;
    }
    showStatus(`پیدا شد: ${payload.repos.length} ریپو در مسیر ${payload.root}`, 'success');
    payload.repos.forEach((repo) => repoContainer.appendChild(renderRepo(repo)));
  } catch (error) {
    showStatus('خطا در ارتباط با سرور.', 'error');
  }
};

form.addEventListener('submit', (event) => {
  event.preventDefault();
  render(rootInput.value.trim());
});

render(rootInput.value.trim());
