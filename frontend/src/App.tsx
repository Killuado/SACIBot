import { type FormEvent, useEffect, useState } from 'react'
import {
  ArrowDownRight,
  ArrowRight,
  Bell,
  Check,
  ChevronRight,
  Cpu,
  Gamepad2,
  Heart,
  House,
  Plus,
  Search,
  ShieldCheck,
  ShoppingBag,
  Sparkles,
  Tag,
  Trash2,
  X,
} from 'lucide-react'
import './App.css'

type Section = 'overview' | 'offers' | 'watchlist'
type Category = 'Todos' | 'Hardware' | 'Periféricos' | 'Jogos'
type SortOption = 'discount' | 'price-low' | 'price-high'

type Promotion = {
  id: string
  title: string
  category: Exclude<Category, 'Todos'>
  price: number
  previousPrice: number
  marketplace: string
  image: string
  alt: string
  tone: string
}

type WatchEntry = {
  id: string
  label: string
  pattern: string
  limit: number
  color: string
}

const promotions: Promotion[] = [
  {
    id: 'rtx-4060',
    title: 'GeForce RTX 4060 Twin Edge',
    category: 'Hardware',
    price: 1899.9,
    previousPrice: 2599.9,
    marketplace: 'KaBuM!',
    image:
      'https://images.unsplash.com/photo-1591488320449-011701bb6704?auto=format&fit=crop&w=1500&q=85',
    alt: 'Placa de vídeo para computador',
    tone: 'lime',
  },
  {
    id: 'headset-hyperx',
    title: 'Headset Cloud III Wireless',
    category: 'Periféricos',
    price: 649.9,
    previousPrice: 899.9,
    marketplace: 'Amazon',
    image:
      'https://images.unsplash.com/photo-1505740420928-5e560c06d30e?auto=format&fit=crop&w=900&q=85',
    alt: 'Fones de ouvido pretos',
    tone: 'coral',
  },
  {
    id: 'monitor-lg',
    title: 'Monitor UltraGear 27” 180 Hz',
    category: 'Hardware',
    price: 1199,
    previousPrice: 1699,
    marketplace: 'Pichau',
    image:
      'https://images.unsplash.com/photo-1527443224154-c4a3942d3acf?auto=format&fit=crop&w=900&q=85',
    alt: 'Monitor gamer sobre uma mesa',
    tone: 'blue',
  },
  {
    id: 'keyboard-keychron',
    title: 'Teclado mecânico K2 Pro',
    category: 'Periféricos',
    price: 429.9,
    previousPrice: 599.9,
    marketplace: 'Amazon',
    image:
      'https://images.unsplash.com/photo-1587829741301-dc798b83add3?auto=format&fit=crop&w=900&q=85',
    alt: 'Teclado mecânico compacto',
    tone: 'violet',
  },
  {
    id: 'elden-ring',
    title: 'Elden Ring: Shadow of the Erdtree',
    category: 'Jogos',
    price: 159.9,
    previousPrice: 249.9,
    marketplace: 'Nuuvem',
    image:
      'https://images.unsplash.com/photo-1542751371-adc38448a05e?auto=format&fit=crop&w=900&q=85',
    alt: 'Setup de jogos iluminado',
    tone: 'amber',
  },
]

const initialWatchlist: WatchEntry[] = [
  {
    id: 'watch-1',
    label: 'RTX 4060',
    pattern: 'rtx\\s?4060',
    limit: 2100,
    color: 'lime',
  },
  {
    id: 'watch-2',
    label: 'Headset sem fio',
    pattern: 'headset.*wireless',
    limit: 700,
    color: 'coral',
  },
  {
    id: 'watch-3',
    label: 'Monitor 180 Hz',
    pattern: 'monitor.*180\\s?hz',
    limit: 1250,
    color: 'blue',
  },
]

const currency = new Intl.NumberFormat('pt-BR', {
  style: 'currency',
  currency: 'BRL',
})

function loadWatchlist(): WatchEntry[] {
  try {
    const saved = window.localStorage.getItem('sacibot-demo-watchlist')
    return saved ? (JSON.parse(saved) as WatchEntry[]) : initialWatchlist
  } catch {
    return initialWatchlist
  }
}

function discountPercent(promotion: Promotion) {
  return Math.round((1 - promotion.price / promotion.previousPrice) * 100)
}

function App() {
  const [section, setSection] = useState<Section>('overview')
  const [category, setCategory] = useState<Category>('Todos')
  const [sortOption, setSortOption] = useState<SortOption>('discount')
  const [search, setSearch] = useState('')
  const [watchlist, setWatchlist] = useState<WatchEntry[]>(loadWatchlist)
  const [modalOpen, setModalOpen] = useState(false)
  const [draftLabel, setDraftLabel] = useState('')
  const [draftPattern, setDraftPattern] = useState('')
  const [draftLimit, setDraftLimit] = useState('')
  const [toastMessage, setToastMessage] = useState('')

  useEffect(() => {
    window.localStorage.setItem('sacibot-demo-watchlist', JSON.stringify(watchlist))
  }, [watchlist])

  useEffect(() => {
    function handleKeyboard(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setModalOpen(false)
        return
      }

      if (!['ArrowRight', 'ArrowDown', 'ArrowLeft', 'ArrowUp'].includes(event.key)) {
        return
      }

      const target = event.target
      if (
        target instanceof HTMLElement &&
        target.closest('input, textarea, select, [contenteditable="true"]')
      ) {
        return
      }

      const controls = Array.from(
        document.querySelectorAll<HTMLElement>('[data-focusable="true"]:not(:disabled)'),
      ).filter((control) => control.getClientRects().length > 0)
      if (!controls.length) return

      const currentIndex = controls.indexOf(document.activeElement as HTMLElement)
      const forward = event.key === 'ArrowRight' || event.key === 'ArrowDown'
      const nextIndex =
        currentIndex === -1
          ? 0
          : (currentIndex + (forward ? 1 : -1) + controls.length) % controls.length
      controls[nextIndex]?.focus()
      event.preventDefault()
    }

    window.addEventListener('keydown', handleKeyboard)
    return () => window.removeEventListener('keydown', handleKeyboard)
  }, [])

  const featured = promotions[0]
  const visiblePromotions = promotions.filter((promotion) => {
    const matchesCategory = category === 'Todos' || promotion.category === category
    const matchesSearch = `${promotion.title} ${promotion.marketplace}`
      .toLocaleLowerCase('pt-BR')
      .includes(search.toLocaleLowerCase('pt-BR'))
    return matchesCategory && matchesSearch
  })
  if (sortOption === 'discount') {
    visiblePromotions.sort((left, right) => discountPercent(right) - discountPercent(left))
  } else if (sortOption === 'price-low') {
    visiblePromotions.sort((left, right) => left.price - right.price)
  } else {
    visiblePromotions.sort((left, right) => right.price - left.price)
  }

  function openWatchModal(promotion?: Promotion) {
    setDraftLabel(promotion?.title ?? '')
    setDraftPattern(promotion?.title.toLocaleLowerCase('pt-BR') ?? '')
    setDraftLimit(promotion?.price.toFixed(2) ?? '')
    setModalOpen(true)
  }

  function saveWatchEntry(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const entry: WatchEntry = {
      id: crypto.randomUUID(),
      label: draftLabel.trim(),
      pattern: draftPattern.trim(),
      limit: Number(draftLimit),
      color: ['lime', 'coral', 'blue'][watchlist.length % 3],
    }
    setWatchlist((current) => [entry, ...current])
    setModalOpen(false)
    showToast('Alerta salvo neste dispositivo.')
  }

  function removeWatchEntry(id: string) {
    setWatchlist((current) => current.filter((entry) => entry.id !== id))
  }

  function showToast(message: string) {
    setToastMessage(message)
    window.setTimeout(() => setToastMessage(''), 2600)
  }

  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="Navegação principal">
        <button
          className="brand-lockup"
          type="button"
          aria-label="SACIBot, início"
          data-focusable="true"
          onClick={() => setSection('overview')}
        >
          <span className="brand-mark"><ShoppingBag size={21} strokeWidth={2.5} /></span>
          <span className="brand-name">SACI<span>BOT</span></span>
        </button>

        <div className="sidebar-label">MENU</div>
        <nav className="primary-nav">
          <button
            className={`nav-item ${section === 'overview' ? 'active' : ''}`}
            type="button"
            data-focusable="true"
            aria-current={section === 'overview' ? 'page' : undefined}
            onClick={() => setSection('overview')}
          >
            <House size={19} /> <span>Visão geral</span>
          </button>
          <button
            className={`nav-item ${section === 'offers' ? 'active' : ''}`}
            type="button"
            data-focusable="true"
            aria-current={section === 'offers' ? 'page' : undefined}
            onClick={() => setSection('offers')}
          >
            <Tag size={19} /> <span>Ofertas</span><span className="nav-count">05</span>
          </button>
          <button
            className={`nav-item ${section === 'watchlist' ? 'active' : ''}`}
            type="button"
            data-focusable="true"
            aria-current={section === 'watchlist' ? 'page' : undefined}
            onClick={() => setSection('watchlist')}
          >
            <Heart size={19} /> <span>Minha watchlist</span>
            <span className="nav-count">{watchlist.length.toString().padStart(2, '0')}</span>
          </button>
        </nav>

        <div className="sidebar-bottom">
          <div className="connection-card">
            <span className="connection-dot" />
            <div><strong>Modo local</strong><small>Dados de demonstração</small></div>
          </div>
          <div className="sidebar-footer">SACIBOT <span>·</span> BUILD 0.1</div>
        </div>
      </aside>

      <div className="workspace">
        <header className="topbar">
          <div className="breadcrumb"><span>PAINEL</span><ChevronRight size={14} /><strong>{section === 'overview' ? 'INÍCIO' : section === 'offers' ? 'OFERTAS' : 'WATCHLIST'}</strong></div>
          <div className="topbar-actions">
            <label className="search-box">
              <Search size={17} />
              <input
                aria-label="Buscar oferta"
                placeholder="Buscar produto ou loja"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
              />
              <kbd>/</kbd>
            </label>
            <span className="topbar-divider" />
            <button className="icon-button notification-button" type="button" aria-label="Notificações" title="Notificações" data-focusable="true" onClick={() => showToast('Nenhuma notificação nova no modo demonstração.')}>
              <Bell size={18} /><i />
            </button>
            <div className="profile-avatar" aria-label="Perfil de demonstração">GS</div>
          </div>
        </header>

        <main className="main-content">
          <div className="page-heading">
            <div>
              <div className="eyebrow"><span className="eyebrow-line" /> CENTRAL DE OFERTAS</div>
              <h1>{section === 'overview' ? 'Radar de ofertas' : section === 'offers' ? 'Todas as ofertas' : 'Minha watchlist'}</h1>
              <p className="page-subtitle">
                {section === 'watchlist'
                  ? 'Seus produtos monitorados e limites de preço.'
                  : 'O que vale a pena levar hoje.'}
              </p>
            </div>
            <div className="heading-status"><span className="live-pulse" /> ATUALIZADO AGORA <span className="status-separator">/</span> DEMO</div>
          </div>

          {section === 'overview' && (
            <section className="featured-deal" aria-label="Oferta em destaque">
              <div className="feature-image" role="img" aria-label={featured.alt} style={{ backgroundImage: `url("${featured.image}")` }} />
              <div className="feature-shade" />
              <div className="feature-content">
                <div className="feature-tags">
                  <span className="feature-kicker"><Sparkles size={13} /> ACHADO DO DIA</span>
                  <span className="discount-tag"><ArrowDownRight size={14} /> {discountPercent(featured)}% OFF</span>
                </div>
                <div className="feature-copy">
                  <div className="feature-category">HARDWARE <span>·</span> {featured.marketplace.toUpperCase()}</div>
                  <h2>{featured.title}</h2>
                  <p>Mais desempenho para o próximo nível.</p>
                  <div className="feature-buy-row">
                    <div className="price-lockup">
                      <strong>{currency.format(featured.price)}</strong>
                      <del>{currency.format(featured.previousPrice)}</del>
                    </div>
                    <button className="primary-button" type="button" data-focusable="true" onClick={() => openWatchModal(featured)}>
                      <Heart size={17} /> Acompanhar preço <ArrowRight size={16} />
                    </button>
                  </div>
                </div>
              </div>
              <div className="feature-side-index"><span>01</span><i /><span>05</span></div>
            </section>
          )}

          {section === 'watchlist' ? (
            <section className="watchlist-page">
              <div className="section-heading watchlist-heading">
                <div><span className="section-overline">SEUS ALERTAS</span><h2>Monitoramento ativo <span>{watchlist.length.toString().padStart(2, '0')}</span></h2></div>
                <button className="outline-button" type="button" data-focusable="true" onClick={() => openWatchModal()}><Plus size={17} /> Novo alerta</button>
              </div>
              {watchlist.length ? (
                <div className="watchlist-table">
                  <div className="watchlist-table-head"><span>PRODUTO / REGEX</span><span>PREÇO MÁXIMO</span><span>STATUS</span><span /></div>
                  {watchlist.map((entry) => (
                    <WatchRow key={entry.id} entry={entry} onRemove={removeWatchEntry} />
                  ))}
                </div>
              ) : (
                <div className="empty-state"><Heart size={25} /><h3>Nenhum alerta por aqui</h3><p>Adicione um produto para acompanhar o preço.</p><button className="primary-button" type="button" data-focusable="true" onClick={() => openWatchModal()}><Plus size={16} /> Criar alerta</button></div>
              )}
            </section>
          ) : (
            <div className="dashboard-grid">
              <section className="offers-section">
                <div className="section-heading">
                  <div><span className="section-overline">SELEÇÃO DO RADAR</span><h2>{section === 'offers' ? 'Ofertas encontradas' : 'Em queda agora'} <span>{visiblePromotions.length.toString().padStart(2, '0')}</span></h2></div>
                  <button className="text-button" type="button" data-focusable="true" onClick={() => setSection('offers')}>Ver todas <ArrowRight size={15} /></button>
                </div>
                <div className="filter-row">
                  <div className="category-tabs" role="group" aria-label="Filtrar por categoria">
                    {(['Todos', 'Hardware', 'Periféricos', 'Jogos'] as Category[]).map((item) => (
                      <button className={`category-tab ${category === item ? 'selected' : ''}`} type="button" data-focusable="true" key={item} onClick={() => setCategory(item)}>{item}</button>
                    ))}
                  </div>
                  <label className="sort-control"><span>ORDEM</span><select aria-label="Ordenar ofertas" data-focusable="true" value={sortOption} onChange={(event) => setSortOption(event.target.value as SortOption)}><option value="discount">Maior desconto</option><option value="price-low">Menor preço</option><option value="price-high">Maior preço</option></select></label>
                </div>
                {visiblePromotions.length ? (
                  <div className="offer-grid">
                    {visiblePromotions.slice(0, section === 'offers' ? 5 : 3).map((promotion) => (
                      <PromotionCard key={promotion.id} promotion={promotion} onWatch={() => openWatchModal(promotion)} />
                    ))}
                  </div>
                ) : (
                  <div className="no-results">Nenhuma oferta encontrada para essa busca.</div>
                )}
                <div className="deal-footnote"><ShieldCheck size={15} /> Ofertas ilustrativas para navegação em modo local.</div>
              </section>

              <aside className="watchlist-panel">
                <div className="panel-heading">
                  <div><span className="section-overline">SEUS ALERTAS</span><h2>Watchlist <span className="panel-count">{watchlist.length.toString().padStart(2, '0')}</span></h2></div>
                  <button className="icon-button small-icon-button" type="button" aria-label="Adicionar alerta" title="Adicionar alerta" data-focusable="true" onClick={() => openWatchModal()}><Plus size={18} /></button>
                </div>
                {watchlist.length ? (
                  <div className="watchlist-list">
                    {watchlist.slice(0, 4).map((entry) => (
                      <WatchRow key={entry.id} entry={entry} onRemove={removeWatchEntry} compact />
                    ))}
                  </div>
                ) : (
                  <div className="watchlist-empty"><Heart size={20} /><p>Adicione seu primeiro alerta de preço.</p></div>
                )}
                <button className="panel-link" type="button" data-focusable="true" onClick={() => setSection('watchlist')}>Abrir watchlist <ArrowRight size={15} /></button>
                <div className="panel-rule" />
                <div className="market-status">
                  <div className="market-status-icon"><Gamepad2 size={17} /></div>
                  <div><strong>Seu radar está ligado</strong><span>O protótipo salva alertas neste navegador.</span></div>
                  <span className="live-pulse" />
                </div>
              </aside>
            </div>
          )}

          <footer className="content-footer">
            <span><span className="footer-dot" /> MODO DEMONSTRAÇÃO</span>
            <span>PREÇOS E OFERTAS FICTÍCIOS <i>·</i> SACIBOT UI 0.1</span>
          </footer>
        </main>
      </div>

      {toastMessage && <div className="toast" role="status"><Check size={16} /> {toastMessage}</div>}

      {modalOpen && (
        <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setModalOpen(false) }}>
          <section className="watch-modal" role="dialog" aria-modal="true" aria-labelledby="modal-title">
            <div className="modal-topline"><span><Heart size={15} /> NOVO ALERTA</span><button className="icon-button" type="button" aria-label="Fechar" title="Fechar" data-focusable="true" onClick={() => setModalOpen(false)}><X size={18} /></button></div>
            <h2 id="modal-title">O que você está procurando?</h2>
            <p>Defina o produto e o preço máximo para este alerta.</p>
            <form onSubmit={saveWatchEntry}>
              <label>Nome do alerta<input autoFocus required maxLength={80} value={draftLabel} onChange={(event) => setDraftLabel(event.target.value)} placeholder="Ex.: Placa de vídeo RTX 4060" /></label>
              <label>Expressão de busca<input required maxLength={200} value={draftPattern} onChange={(event) => setDraftPattern(event.target.value)} placeholder="Ex.: rtx\\s?4060" /></label>
              <label>Preço máximo<div className="price-input"><span>R$</span><input required type="number" min="0.01" step="0.01" value={draftLimit} onChange={(event) => setDraftLimit(event.target.value)} placeholder="2.100,00" /></div></label>
              <div className="modal-actions"><button className="cancel-button" type="button" data-focusable="true" onClick={() => setModalOpen(false)}>Cancelar</button><button className="primary-button" type="submit" data-focusable="true"><Check size={16} /> Salvar alerta</button></div>
            </form>
          </section>
        </div>
      )}
    </div>
  )
}

function PromotionCard({ promotion, onWatch }: { promotion: Promotion; onWatch: () => void }) {
  return (
    <article className="offer-card">
      <div className={`offer-image ${promotion.tone}`} role="img" aria-label={promotion.alt} style={{ backgroundImage: `url("${promotion.image}")` }}>
        <span className="offer-discount">-{discountPercent(promotion)}%</span>
        <button className="offer-save" type="button" aria-label={`Monitorar ${promotion.title}`} title="Adicionar à watchlist" data-focusable="true" onClick={onWatch}><Heart size={16} /></button>
      </div>
      <div className="offer-details">
        <div className="offer-store"><span className="store-mark">{promotion.marketplace.slice(0, 1)}</span>{promotion.marketplace}<span className="store-verified"><ShieldCheck size={12} /></span></div>
        <h3>{promotion.title}</h3>
        <div className="offer-price-row"><strong>{currency.format(promotion.price)}</strong><del>{currency.format(promotion.previousPrice)}</del></div>
        <div className="offer-card-bottom"><span><ArrowDownRight size={13} /> menor preço demo</span><button type="button" aria-label={`Acompanhar ${promotion.title}`} title="Acompanhar preço" data-focusable="true" onClick={onWatch}><ArrowRight size={16} /></button></div>
      </div>
    </article>
  )
}

function WatchRow({ entry, onRemove, compact = false }: { entry: WatchEntry; onRemove: (id: string) => void; compact?: boolean }) {
  return (
    <article className={`watch-row ${compact ? 'compact' : ''}`}>
      <span className={`watch-indicator ${entry.color}`}><Cpu size={17} /></span>
      <div className="watch-copy"><strong>{entry.label}</strong><span>{compact ? `até ${currency.format(entry.limit)}` : entry.pattern}</span></div>
      {!compact && <div className="watch-limit"><span>PREÇO MÁXIMO</span><strong>{currency.format(entry.limit)}</strong></div>}
      {!compact && <span className="watch-active"><i /> ATIVO</span>}
      <button className="remove-watch" type="button" aria-label={`Remover ${entry.label}`} title="Remover alerta" data-focusable="true" onClick={() => onRemove(entry.id)}><Trash2 size={16} /></button>
    </article>
  )
}

export default App
