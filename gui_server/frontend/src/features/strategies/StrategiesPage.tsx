import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import Cropper, { type Area } from 'react-easy-crop'
import { Expand } from 'lucide-react'
import { getApi } from '../../api/client'
import { TEMPLATE_SLOTS, type TemplateSlot, type TemplateSourceImage } from '../../api/types'
import { Button, Card, Lightbox, Select, Spinner, TextField } from '../../components/primitives'

const SOURCE_POSITIONS = [0, 1, 2, 3] as const

const SLOT_LABELS: Record<TemplateSlot, string> = {
  bullish_ideal: 'Bullish Ideal',
  bearish_ideal: 'Bearish Ideal',
  fail_trap: 'Fail / Trap',
}

function readFileAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result as string)
    reader.onerror = reject
    reader.readAsDataURL(file)
  })
}

function NewStrategyDialog({ existingNames, onClose, onCreated }: {
  existingNames: string[]; onClose: () => void; onCreated: (id: string) => void
}) {
  const [name, setName] = useState('')
  const [category, setCategory] = useState('')
  const [error, setError] = useState('')

  const createMutation = useMutation({
    mutationFn: async () => (await getApi()).create_strategy(name.trim(), category.trim()),
    onSuccess: (result) => {
      if ('error' in result) { setError(result.error); return }
      onCreated(result.id)
    },
  })

  const submit = () => {
    const trimmed = name.trim()
    if (!trimmed) { setError('Name is required.'); return }
    if (existingNames.some((n) => n.toLowerCase() === trimmed.toLowerCase())) {
      setError(`A strategy named '${trimmed}' already exists.`); return
    }
    createMutation.mutate()
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <Card square className="w-80 p-3 flex flex-col gap-3" onClick={(e) => e.stopPropagation()}>
        <h2 className="text-[11px] font-semibold tracking-[0.14em] uppercase text-text-secondary">New Strategy</h2>
        <TextField label="Name" value={name} onChange={(e) => setName(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && submit()} autoFocus />
        <TextField label="Category (optional)" value={category} onChange={(e) => setCategory(e.target.value)} />
        {error && <p className="text-xs text-error">{error}</p>}
        <div className="flex gap-2 mt-1">
          <Button variant="primary" onClick={submit} disabled={createMutation.isPending}>Create</Button>
          <Button onClick={onClose}>Cancel</Button>
        </div>
      </Card>
    </div>
  )
}

/** Locks the crop rectangle to the eventual composite cell's aspect ratio and
 * lets the user pan/zoom to pick it — mirrors gui/widgets/crop_dialog.py's
 * role, but against the web Cropper instead of a Tk canvas. The rectangle it
 * produces is normalized (0..1 fractions of the *original* image), matching
 * exactly what LocalFileTemplateImageStore.save_template_source expects —
 * the backend stores the full source image and re-crops at composite time,
 * so this modal never touches pixels itself. */
function CropModal({ imageSrc, aspect, initialArea, busy, onCancel, onConfirm }: {
  imageSrc: string; aspect: number; initialArea?: Area; busy: boolean
  onCancel: () => void; onConfirm: (box: { x: number; y: number; w: number; h: number }) => void
}) {
  const [crop, setCrop] = useState({ x: 0, y: 0 })
  const [zoom, setZoom] = useState(1)
  const areaRef = useRef<Area | null>(initialArea ?? null)

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-6" onClick={() => !busy && onCancel()}>
      <Card square className="w-130 max-w-full p-3 flex flex-col gap-3" onClick={(e) => e.stopPropagation()}>
        <h2 className="text-[11px] font-semibold tracking-widest uppercase text-text-secondary">Position Crop</h2>
        <div className="relative w-full h-80 bg-black">
          <Cropper
            image={imageSrc}
            crop={crop}
            zoom={zoom}
            aspect={aspect}
            initialCroppedAreaPercentages={initialArea}
            onCropChange={setCrop}
            onZoomChange={setZoom}
            onCropComplete={(area) => { areaRef.current = area }}
          />
        </div>
        <label className="flex items-center gap-3 text-xs text-text-secondary">
          Zoom
          <input type="range" min={1} max={3} step={0.01} value={zoom} onChange={(e) => setZoom(Number(e.target.value))} className="flex-1 accent-(--accent)" />
        </label>
        <div className="flex gap-2 justify-end">
          <Button onClick={onCancel} disabled={busy}>Cancel</Button>
          <Button
            variant="primary" disabled={busy}
            onClick={() => {
              const a = areaRef.current
              if (a) onConfirm({ x: a.x / 100, y: a.y / 100, w: a.width / 100, h: a.height / 100 })
            }}
          >
            {busy ? 'Saving…' : 'Use Crop'}
          </Button>
        </div>
      </Card>
    </div>
  )
}

/** Full-size caption editor — the inline textarea is deliberately small (it
 * swaps with the configure grid without changing the card's height), so this
 * is the escape hatch for comfortably writing a longer caption. */
function CaptionModal({ initialValue, busy, onCancel, onSave }: {
  initialValue: string; busy: boolean; onCancel: () => void; onSave: (text: string) => void
}) {
  const [value, setValue] = useState(initialValue)
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-6" onClick={() => !busy && onCancel()}>
      <Card square className="w-160 max-w-full p-3 flex flex-col gap-3" onClick={(e) => e.stopPropagation()}>
        <h2 className="text-[11px] font-semibold tracking-widest uppercase text-text-secondary">Caption — context for the AI</h2>
        <textarea
          value={value} onChange={(e) => setValue(e.target.value)} rows={14} autoFocus
          placeholder="Describe what this setup shows and why it matters..."
          className="bg-ground border border-border p-3 text-sm leading-relaxed resize-y focus:outline-none focus:border-accent"
        />
        <div className="flex gap-2 justify-end">
          <Button onClick={onCancel} disabled={busy}>Cancel</Button>
          <Button variant="primary" disabled={busy} onClick={() => onSave(value)}>{busy ? 'Saving…' : 'Save Caption'}</Button>
        </div>
      </Card>
    </div>
  )
}

type PendingCrop = { position: number; imageSrc: string; aspect: number; initialArea?: Area }

/** count = how many of the slot's up-to-4 positions will be filled once this
 * one is saved; index = targetPosition's 0-based rank among all filled
 * positions in ascending order — matches template_compositor.py's own
 * `sorted(sources, key=position)` fill order exactly, so the crop aspect
 * ratio always matches the cell the image will actually land in. */
function countAndIndex(existingPositions: number[], targetPosition: number) {
  const filled = new Set(existingPositions)
  filled.add(targetPosition)
  const sorted = [...filled].sort((a, b) => a - b)
  return { count: sorted.length, index: sorted.indexOf(targetPosition) }
}

function TemplateSlotCard({ strategyId, slot, record, onChanged, onStatusMessage, layout = 'stacked' }: {
  strategyId: string; slot: TemplateSlot; record: { image: string | null; caption: string } | null | undefined
  onChanged: () => Promise<unknown>; onStatusMessage: (msg: string) => void; layout?: 'stacked' | 'wide'
}) {
  const [caption, setCaption] = useState(record?.caption ?? '')
  const fileRefs = useRef<Record<number, HTMLInputElement | null>>({})
  const [pending, setPending] = useState<PendingCrop | null>(null)
  const [configuring, setConfiguring] = useState(false)
  const [lightboxOpen, setLightboxOpen] = useState(false)
  const [captionModalOpen, setCaptionModalOpen] = useState(false)
  // Covers the gap between the backend finishing the save+stitch and the
  // refreshed thumbnail actually landing in `record` -- without this, the
  // crop modal was closing (and its own "Saving..." indicator disappearing)
  // one network round-trip before the new image was actually visible,
  // which read as "did this even do anything?".
  const [awaitingRefresh, setAwaitingRefresh] = useState(false)
  useEffect(() => setCaption(record?.caption ?? ''), [record?.caption])

  const { data: sources, refetch: refetchSources } = useQuery({
    queryKey: ['template-sources', strategyId, slot],
    queryFn: async () => (await getApi()).get_template_sources(strategyId, slot),
  })
  const byPosition = new Map((sources ?? []).map((s) => [s.position, s]))

  const saveMutation = useMutation({
    mutationFn: async (args: { position: number; imageBase64: string; box: { x: number; y: number; w: number; h: number } }) =>
      (await getApi()).save_template_source(strategyId, slot, args.position, args.imageBase64, args.box.x, args.box.y, args.box.w, args.box.h, caption || SLOT_LABELS[slot]),
    onSuccess: async () => {
      setAwaitingRefresh(true)
      await Promise.all([refetchSources(), onChanged()])
      setAwaitingRefresh(false)
      setPending(null)
      onStatusMessage(`${SLOT_LABELS[slot]} image saved and re-stitched`)
    },
  })
  const busy = saveMutation.isPending || awaitingRefresh
  const captionMutation = useMutation({
    mutationFn: async (text: string) => (await getApi()).update_template_caption(strategyId, slot, text),
    onSuccess: () => { onChanged(); onStatusMessage(`${SLOT_LABELS[slot]} caption saved`) },
  })
  const removeMutation = useMutation({
    mutationFn: async (position: number) => (await getApi()).remove_template_source(strategyId, slot, position),
    onSuccess: () => { refetchSources(); onChanged(); onStatusMessage(`${SLOT_LABELS[slot]} image removed`) },
  })

  const beginAdd = async (position: number, file: File) => {
    const dataUrl = await readFileAsDataUrl(file)
    const { count, index } = countAndIndex((sources ?? []).map((s) => s.position), position)
    const aspect = await (await getApi()).get_cell_aspect_ratio(count, index)
    setPending({ position, imageSrc: dataUrl, aspect })
  }

  const beginEdit = async (source: TemplateSourceImage) => {
    if (!source.image) return
    const { count, index } = countAndIndex((sources ?? []).map((s) => s.position), source.position)
    const aspect = await (await getApi()).get_cell_aspect_ratio(count, index)
    setPending({
      position: source.position, imageSrc: source.image, aspect,
      initialArea: { x: source.crop_x * 100, y: source.crop_y * 100, width: source.crop_w * 100, height: source.crop_h * 100 },
    })
  }

  const preview = (
    <div className="relative w-full h-30 bg-ground border border-border flex items-center justify-center overflow-hidden group">
      {record?.image
        ? <img src={record.image} alt={slot} className="object-cover w-full h-full" />
        : <span className="text-[11px] text-text-disabled px-2 text-center">No reference image yet</span>}
      {record?.image && !busy && (
        <button
          onClick={() => setLightboxOpen(true)}
          aria-label="View full size"
          className="absolute bottom-1 right-1 flex h-6 w-6 items-center justify-center bg-black/55 text-white opacity-0 group-hover:opacity-100 transition"
        >
          <Expand size={12} />
        </button>
      )}
      {busy && (
        <div className="absolute inset-0 flex items-center justify-center gap-2 bg-black/60 text-[11px] font-medium uppercase tracking-wide text-white">
          <Spinner /> Stitching…
        </div>
      )}
    </div>
  )

  // Fills the same fixed-height box the caption textarea occupies when
  // toggled via "Configure" -- swapping in place instead of appending below
  // it, so opening/closing it never changes the card's total height.
  const grid = (
    <div className="grid grid-cols-2 grid-rows-2 gap-1.5 h-full">
      {SOURCE_POSITIONS.map((pos) => {
        const source = byPosition.get(pos)
        const savingThis = busy && pending?.position === pos
        return (
          <div key={pos} className="relative bg-ground border border-border overflow-hidden group">
            {savingThis && (
              <div className="absolute inset-0 z-10 flex items-center justify-center bg-black/60">
                <Spinner className="text-white" />
              </div>
            )}
            {source?.image ? (
              <>
                <button className="w-full h-full" onClick={() => beginEdit(source)} title="Re-crop">
                  <img src={source.image} className="object-cover w-full h-full" alt={`${slot} source ${pos}`} />
                </button>
                <button
                  onClick={() => removeMutation.mutate(pos)}
                  className="absolute top-0.5 right-0.5 w-4 h-4 flex items-center justify-center bg-black/60 text-white text-[10px] opacity-0 group-hover:opacity-100 transition"
                  aria-label={`Remove image ${pos + 1}`}
                >
                  ×
                </button>
              </>
            ) : (
              <button
                onClick={() => fileRefs.current[pos]?.click()}
                className="w-full h-full flex items-center justify-center text-text-disabled text-base hover:text-accent transition"
                aria-label={`Add image ${pos + 1}`}
              >
                +
              </button>
            )}
            <input
              ref={(el) => { fileRefs.current[pos] = el }}
              type="file" accept="image/*" className="hidden"
              onChange={(e) => { const f = e.target.files?.[0]; if (f) beginAdd(pos, f); e.target.value = '' }}
            />
          </div>
        )
      })}
    </div>
  )

  const saveCaption = () => captionMutation.mutate(caption)

  const editorBlock = (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between">
        <span className="text-[11px] tracking-[0.08em] uppercase text-text-secondary">
          {configuring ? 'Source Images' : 'Caption — context for the AI'}
        </span>
        {!configuring && (
          <button onClick={() => setCaptionModalOpen(true)} aria-label="Expand caption editor" className="text-text-disabled hover:text-accent transition">
            <Expand size={11} />
          </button>
        )}
      </div>

      <div className="h-24">
        {configuring
          ? grid
          : (
            <textarea
              value={caption} onChange={(e) => setCaption(e.target.value)}
              placeholder="Describe what this setup shows and why it matters..."
              className="h-full w-full bg-ground border border-border p-2.5 text-xs leading-relaxed resize-none focus:outline-none focus:border-accent"
            />
          )}
      </div>

      <div className="flex items-center justify-between">
        <Button onClick={() => setConfiguring((c) => !c)}>Configure</Button>
        {configuring
          ? <Button variant="primary" onClick={() => setConfiguring(false)}>Save Images</Button>
          : <Button variant="primary" onClick={saveCaption} disabled={!record?.image}>Save Caption</Button>}
      </div>
    </div>
  )

  const modal = pending && (
    <CropModal
      imageSrc={pending.imageSrc} aspect={pending.aspect} initialArea={pending.initialArea}
      busy={busy}
      onCancel={() => setPending(null)}
      onConfirm={(box) => saveMutation.mutate({ position: pending.position, imageBase64: pending.imageSrc, box })}
    />
  )

  const lightbox = lightboxOpen && record?.image && (
    <Lightbox
      src={record.image} alt={`${SLOT_LABELS[slot]} composite`} onClose={() => setLightboxOpen(false)}
      downloadName={`${slot}-composite.jpg`}
    />
  )

  const captionModal = captionModalOpen && (
    <CaptionModal
      initialValue={caption} busy={captionMutation.isPending}
      onCancel={() => setCaptionModalOpen(false)}
      onSave={(text) => { setCaption(text); captionMutation.mutate(text); setCaptionModalOpen(false) }}
    />
  )

  if (layout === 'wide') {
    // Slot label sits beside the image (not above the whole row), so it
    // lines up horizontally with the caption label on the right instead of
    // adding its own row -- one less row of height on the page that most
    // needed to fit without scrolling.
    return (
      <div className="grid grid-cols-2 gap-4">
        <div className="flex flex-col gap-2">
          <h3 className="text-[11px] font-semibold tracking-widest uppercase text-accent">{SLOT_LABELS[slot]}</h3>
          {preview}
        </div>
        <div className="min-w-0">{editorBlock}</div>
        {modal}
        {lightbox}
        {captionModal}
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-3">
      <h3 className="text-[11px] font-semibold tracking-widest uppercase text-accent">{SLOT_LABELS[slot]}</h3>
      {preview}
      {editorBlock}
      {modal}
      {lightbox}
      {captionModal}
    </div>
  )
}

function PromptSection({ strategyId, onChanged }: { strategyId: string; onChanged: () => Promise<unknown> }) {
  const { data: prompt } = useQuery({ queryKey: ['prompt', strategyId], queryFn: async () => (await getApi()).get_prompt(strategyId) })
  const { data: versions } = useQuery({ queryKey: ['prompt-versions', strategyId], queryFn: async () => (await getApi()).list_prompt_versions(strategyId) })
  const [text, setText] = useState('')
  const [showHistory, setShowHistory] = useState(false)
  useEffect(() => setText(prompt?.text ?? ''), [prompt?.text])

  const saveMutation = useMutation({
    mutationFn: async () => (await getApi()).save_prompt(strategyId, text, 'edited via web UI'),
    onSuccess: onChanged,
  })

  return (
    <div className="flex h-full flex-col gap-3">
      <div className="flex items-center justify-between">
        <h3 className="text-[11px] font-semibold tracking-widest uppercase text-text-secondary">
          Agent 2 Prompt {prompt && <span className="font-mono normal-case tracking-normal text-text-disabled">v{prompt.version}</span>}
        </h3>
        <button className="text-[11px] font-semibold tracking-wide uppercase text-accent hover:text-accent-hover" onClick={() => setShowHistory((s) => !s)}>
          {showHistory ? 'Hide history' : `History (${versions?.length ?? 0})`}
        </button>
      </div>
      <textarea
        value={text} onChange={(e) => setText(e.target.value)} rows={14}
        className="flex-1 min-h-64 bg-ground border border-border p-3 text-xs font-mono leading-relaxed resize-y focus:outline-none focus:border-accent"
        placeholder="No prompt saved yet."
      />
      <Button variant="primary" className="self-start" onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending}>
        Save as New Version
      </Button>
      {showHistory && (
        <div className="border-t border-border pt-2 flex flex-col gap-1 max-h-48 overflow-auto">
          {(versions ?? []).slice().reverse().map((v) => (
            <button key={v.version} onClick={() => setText(v.text)} className="text-left text-xs px-2 py-1 hover:bg-surface-alt">
              v{v.version} — {new Date(v.created_at).toLocaleString()} {v.notes && `(${v.notes})`}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

export default function StrategiesPage({ onStatusMessage }: { onStatusMessage: (msg: string) => void }) {
  const qc = useQueryClient()
  const [activeId, setActiveId] = useState<string | null>(null)
  const [showNewDialog, setShowNewDialog] = useState(false)

  const { data: strategies } = useQuery({ queryKey: ['strategies'], queryFn: async () => (await getApi()).list_strategies() })
  const { data: initialActive } = useQuery({ queryKey: ['active-strategy'], queryFn: async () => (await getApi()).get_active_strategy() })

  useEffect(() => {
    if (!activeId && initialActive) setActiveId(initialActive.id)
    else if (!activeId && strategies?.length) setActiveId(strategies[0].id)
  }, [initialActive, strategies, activeId])

  const { data: templates, refetch: refetchTemplates } = useQuery({
    queryKey: ['templates', activeId],
    queryFn: async () => (await getApi()).get_strategy_templates(activeId!),
    enabled: !!activeId,
  })

  const switchMutation = useMutation({
    mutationFn: async (id: string) => (await getApi()).set_active_strategy(id),
    onSuccess: (_ok, id) => {
      setActiveId(id)
      const name = strategies?.find((s) => s.id === id)?.name
      onStatusMessage(`Strategy '${name}' is now active`)
    },
  })

  // Returns a promise so callers that need the fresh data on screen before
  // dismissing their own UI (e.g. the crop modal) can await it, instead of
  // firing it off and closing immediately while the old thumbnail is still showing.
  const refreshAll = () => Promise.all([
    refetchTemplates(),
    qc.invalidateQueries({ queryKey: ['prompt', activeId] }),
    qc.invalidateQueries({ queryKey: ['prompt-versions', activeId] }),
  ])

  const selectorBar = (
    <>
      <Select
        label="Active strategy" value={activeId ?? ''} className="w-72 h-10"
        style={{ fontSize: '15px', fontWeight: 600 }}
        onChange={(e) => switchMutation.mutate(e.target.value)}
      >
        {(strategies ?? []).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
      </Select>
      <Button variant="primary" className="h-10" onClick={() => setShowNewDialog(true)}>+ New Strategy</Button>
    </>
  )

  return (
    <div className="flex flex-col gap-5">
      {showNewDialog && (
        <NewStrategyDialog
          existingNames={(strategies ?? []).map((s) => s.name)}
          onClose={() => setShowNewDialog(false)}
          onCreated={(id) => {
            setShowNewDialog(false)
            setActiveId(id)
            qc.invalidateQueries({ queryKey: ['strategies'] })
            onStatusMessage('Strategy created')
          }}
        />
      )}

      {!strategies?.length && (
        <>
          <div className="flex items-end gap-3">{selectorBar}</div>
          <Card className="p-10 flex flex-col items-center gap-3 text-center">
            <p className="text-sm text-text-secondary max-w-xs">
              No strategies yet. A strategy bundles reference chart images and an Agent 2 prompt the live filter checks every trigger against.
            </p>
            <Button variant="primary" onClick={() => setShowNewDialog(true)}>+ New Strategy</Button>
          </Card>
        </>
      )}

      {activeId && strategies?.length ? (
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_1fr_1.6fr] gap-x-6 gap-y-6">
          <div className="lg:col-start-1 lg:col-span-2 lg:row-start-1 flex items-end gap-3">
            {selectorBar}
          </div>

          <div className="lg:col-start-1 lg:row-start-2">
            <TemplateSlotCard strategyId={activeId} slot={TEMPLATE_SLOTS[0]} record={templates?.[TEMPLATE_SLOTS[0]]} onChanged={refreshAll} onStatusMessage={onStatusMessage} />
          </div>
          <div className="lg:col-start-2 lg:row-start-2 lg:border-l lg:border-divider/15">
            <TemplateSlotCard strategyId={activeId} slot={TEMPLATE_SLOTS[1]} record={templates?.[TEMPLATE_SLOTS[1]]} onChanged={refreshAll} onStatusMessage={onStatusMessage} />
          </div>
          <div className="lg:col-start-3 lg:row-start-1 lg:row-span-3 lg:border-l lg:border-divider/15 lg:pl-6">
            <PromptSection strategyId={activeId} onChanged={refreshAll} />
          </div>
          <div className="lg:col-start-1 lg:col-span-2 lg:row-start-3 lg:border-t lg:border-divider/15 lg:pt-6">
            <TemplateSlotCard strategyId={activeId} slot={TEMPLATE_SLOTS[2]} record={templates?.[TEMPLATE_SLOTS[2]]} onChanged={refreshAll} onStatusMessage={onStatusMessage} layout="wide" />
          </div>
        </div>
      ) : null}
    </div>
  )
}
