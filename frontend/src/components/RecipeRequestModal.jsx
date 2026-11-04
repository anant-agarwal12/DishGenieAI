import { useEffect } from 'react'
import { Check, Loader2, Pencil, Sparkles, X } from 'lucide-react'
import { INGREDIENT_EMOJIS, formatIngredientName } from '../services/api'

// Review dialog shown after the user clicks Generate: lets them accept or go back and edit.
export default function RecipeRequestModal({ requestPayload, isLoading = false, onClose, onEdit, onAccept }) {
  useEffect(() => {
    if (!requestPayload) return undefined
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [requestPayload, onClose])

  if (!requestPayload) return null
  const { ingredients, preferences: p } = requestPayload

  const rows = [
    ['Diet', p.diet],
    ['Cuisine', p.cuisine],
    ['Cooking time', `${p.cookingTime} min`],
    ['Skill level', p.difficulty],
    ['Servings', p.servings],
  ]
  if (p.additionalIngredients) rows.push(['Extra pantry items', p.additionalIngredients])

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-stone-900/60 backdrop-blur-xs animate-in fade-in duration-200"
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-title"
    >
      <div className="bg-white rounded-3xl w-full max-w-lg shadow-2xl border border-stone-200 animate-in zoom-in-95 duration-200 overflow-hidden">
        <div className="flex items-start justify-between gap-3 px-6 pt-6 pb-4">
          <div className="flex items-center gap-3">
            <div className="w-11 h-11 rounded-2xl bg-orange-50 border border-orange-200 flex items-center justify-center text-orange-600">
              <Sparkles className="w-5 h-5" aria-hidden="true" />
            </div>
            <div>
              <h3 id="confirm-title" className="text-lg font-extrabold text-stone-900 leading-tight">
                Ready to cook?
              </h3>
              <p className="text-xs text-stone-500">Check your choices, then generate.</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-xl text-stone-400 hover:text-stone-700 hover:bg-stone-100 transition-colors cursor-pointer"
            aria-label="Close"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="px-6 space-y-4">
          <div>
            <p className="text-[11px] font-bold uppercase tracking-wider text-stone-500 mb-2">
              Ingredients ({ingredients.length})
            </p>
            <div className="flex flex-wrap gap-2">
              {ingredients.map((ing) => (
                <span
                  key={ing}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-stone-50 border border-stone-200 text-xs font-bold text-stone-800"
                >
                  <span aria-hidden="true">{INGREDIENT_EMOJIS[ing] || '🥗'}</span>
                  {formatIngredientName(ing)}
                </span>
              ))}
            </div>
          </div>

          <dl className="grid grid-cols-2 gap-px rounded-2xl overflow-hidden border border-stone-200 bg-stone-200 text-xs">
            {rows.map(([label, value], idx) => (
              <div key={label} className={`bg-white px-3.5 py-2.5 ${rows.length % 2 === 1 && idx === rows.length - 1 ? 'col-span-2' : ''}`}>
                <dt className="text-[11px] text-stone-400">{label}</dt>
                <dd className="font-bold text-stone-900">{value}</dd>
              </div>
            ))}
          </dl>
        </div>

        <div className="flex flex-col-reverse sm:flex-row items-center justify-end gap-3 px-6 py-5 mt-2">
          <button
            type="button"
            onClick={onEdit}
            disabled={isLoading}
            className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-xl text-sm font-bold text-stone-700 bg-stone-100 hover:bg-stone-200 transition-colors cursor-pointer disabled:opacity-50"
          >
            <Pencil className="w-4 h-4" aria-hidden="true" />
            Edit
          </button>
          <button
            type="button"
            onClick={onAccept}
            disabled={isLoading}
            autoFocus
            className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-6 py-2.5 rounded-xl text-sm font-bold text-white bg-gradient-to-r from-orange-500 to-amber-600 hover:from-orange-600 hover:to-amber-700 shadow-md shadow-orange-500/20 transition-colors cursor-pointer disabled:opacity-70"
          >
            {isLoading ? <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" /> : <Check className="w-4 h-4" aria-hidden="true" />}
            {isLoading ? 'Finding dishes…' : 'Accept & Generate'}
          </button>
        </div>
      </div>
    </div>
  )
}
