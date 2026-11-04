import { useState, useEffect } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import {
  ArrowLeft,
  Sparkles,
  Clock,
  Flame,
  Users,
  ChefHat,
  Utensils,
  CheckSquare,
  Square,
  Printer,
  RotateCcw,
  Copy,
  Check,
  AlertCircle,
  BookOpen,
  ShoppingBag,
  Heart,
} from 'lucide-react'
import {
  getRecipeById,
  toggleFavorite,
  HISTORY_UPDATE_EVENT,
} from '../services/storage'
import Toast from '../components/Toast'

// Defense-in-depth sanitization to ensure no stray markdown formatting is displayed
function cleanText(str) {
  if (!str) return ''
  return String(str).replace(/[*_#`~]/g, '').trim()
}

export default function Recipe() {
  const location = useLocation()
  const navigate = useNavigate()

  // Retrieve passed state, with sessionStorage fallback to survive browser refresh
  const [recipePayload, setRecipePayload] = useState(() => {
    // If opened directly from History or Favorites via saved recipeRecord
    if (location.state?.recipeRecord) {
      const rec = location.state.recipeRecord
      const payload = {
        recipeData: {
          recipe: {
            name: rec.name,
            description: rec.description,
            ingredients: rec.ingredients,
            instructions: rec.instructions,
            substitutions: rec.substitutions,
            shopping_list: rec.shopping_list,
          },
          raw_text: rec.raw_text,
        },
        preferences: rec.preferences,
        confirmedIngredients: rec.confirmedIngredients,
        savedId: rec.id,
        isFavorite: rec.isFavorite,
      }
      sessionStorage.setItem('dishgenie_recipe_data', JSON.stringify(payload))
      return payload
    }

    // If navigated from Detect
    if (location.state?.recipeData) {
      const payload = {
        recipeData: location.state.recipeData,
        preferences: location.state.preferences,
        confirmedIngredients: location.state.confirmedIngredients,
        savedId: location.state.savedRecord?.id,
        isFavorite: location.state.savedRecord?.isFavorite || false,
        selectedDish: location.state.selectedDish || location.state?.recipeRecord?.selectedDish || null,
      }
      sessionStorage.setItem('dishgenie_recipe_data', JSON.stringify(payload))
      return payload
    }

    const cached = sessionStorage.getItem('dishgenie_recipe_data')
    if (cached) {
      try {
        return JSON.parse(cached)
      } catch {
        return null
      }
    }
    return null
  })

  // Favorite status state with real-time synchronization
  const [isFavorite, setIsFavorite] = useState(() => {
    if (recipePayload?.savedId) {
      const record = getRecipeById(recipePayload.savedId)
      if (record) return record.isFavorite
    }
    return recipePayload?.isFavorite || false
  })

  // Checked state for interactive shopping list
  const [checkedItems, setCheckedItems] = useState({})
  const [copied, setCopied] = useState(false)
  const [toast, setToast] = useState(null)
  const [tab, setTab] = useState('steps')

  // Synchronize favorite status on external updates (e.g. cross-tab or history page)
  useEffect(() => {
    if (!recipePayload?.savedId) return

    const handleSync = () => {
      const record = getRecipeById(recipePayload.savedId)
      if (record) {
        setIsFavorite(record.isFavorite)
      }
    }

    window.addEventListener(HISTORY_UPDATE_EVENT, handleSync)
    window.addEventListener('storage', handleSync)

    return () => {
      window.removeEventListener(HISTORY_UPDATE_EVENT, handleSync)
      window.removeEventListener('storage', handleSync)
    }
  }, [recipePayload?.savedId])

  // Scroll to top on page load
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }, [])

  // Handle toggling favorite
  const handleToggleFavorite = () => {
    if (recipePayload?.savedId) {
      const newStatus = toggleFavorite(recipePayload.savedId)
      setIsFavorite(newStatus)
      const updated = { ...recipePayload, isFavorite: newStatus }
      setRecipePayload(updated)
      sessionStorage.setItem('dishgenie_recipe_data', JSON.stringify(updated))
      setToast({
        text: newStatus ? 'Recipe favorited' : 'Removed from favorites',
        type: newStatus ? 'favorite' : 'success',
      })
    }
  }

  // If no recipe data is found (Direct /recipe access without generating)
  if (!recipePayload || !recipePayload.recipeData) {
    return (
      <div className="min-h-[75vh] flex items-center justify-center px-4 py-16 animate-in fade-in duration-200">
        <div className="max-w-md w-full bg-white rounded-3xl p-8 sm:p-10 border border-stone-200 shadow-xl shadow-stone-900/5 text-center space-y-6">
          <div className="relative w-20 h-20 mx-auto flex items-center justify-center">
            <div className="absolute inset-0 rounded-3xl bg-amber-100/60 blur-lg animate-pulse"></div>
            <div className="relative w-20 h-20 rounded-3xl bg-amber-50 border border-amber-200 flex items-center justify-center text-orange-600 shadow-inner">
              <ChefHat className="w-10 h-10" />
            </div>
          </div>

          <div className="space-y-2">
            <h2 className="text-2xl sm:text-3xl font-extrabold text-stone-900 tracking-tight">
              No recipe available yet.
            </h2>
            <p className="text-sm text-stone-600 leading-relaxed max-w-sm mx-auto">
              Generate a recipe using your ingredients and preferences.
            </p>
          </div>

          <div className="pt-2 flex flex-col sm:flex-row items-center justify-center gap-3">
            <button
              type="button"
              onClick={() => navigate('/detect')}
              className="w-full sm:w-auto inline-flex items-center justify-center gap-2.5 px-7 py-3.5 rounded-full text-sm font-bold text-white bg-gradient-to-r from-orange-500 to-amber-600 hover:from-orange-600 hover:to-amber-700 shadow-md shadow-orange-500/25 hover:shadow-orange-500/35 transition-all hover:-translate-y-0.5 cursor-pointer"
            >
              <Sparkles className="w-4 h-4" />
              <span>Start Cooking</span>
            </button>

            <button
              type="button"
              onClick={() => navigate('/')}
              className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-6 py-3.5 rounded-full text-sm font-semibold text-stone-700 bg-stone-100 hover:bg-stone-200 transition-colors cursor-pointer"
            >
              <ArrowLeft className="w-4 h-4" />
              <span>Back to Home</span>
            </button>
          </div>
        </div>
      </div>
    )
  }

  const { recipeData, preferences, confirmedIngredients = [] } = recipePayload
  const { recipe, raw_text } = recipeData

  // Interactive shopping list toggle
  const toggleShoppingItem = (index) => {
    setCheckedItems((prev) => ({
      ...prev,
      [index]: !prev[index],
    }))
  }

  // Clear all checked items
  const handleClearCompleted = () => {
    setCheckedItems({})
  }

  // Copy recipe to clipboard
  const handleCopyRecipe = () => {
    let fullText = ''
    if (recipe) {
      fullText = `🍲 ${recipe.name}\n${recipe.description || ''}\n\n` +
        `⏱ Time: ${preferences?.cookingTime || 30} min | 👥 Servings: ${preferences?.servings || 2} | 🥗 Diet: ${preferences?.diet || 'Custom'} | 🍽 Cuisine: ${preferences?.cuisine || 'Custom'}\n\n` +
        `INGREDIENTS:\n${(recipe.ingredients || []).map((i) => `• ${i}`).join('\n')}\n\n` +
        `INSTRUCTIONS:\n${(recipe.instructions || []).map((step, idx) => `${idx + 1}. ${step}`).join('\n')}`
    } else {
      fullText = raw_text || 'No recipe content available.'
    }
    navigator.clipboard.writeText(fullText)
    setCopied(true)
    setToast({ text: 'Recipe copied to clipboard', type: 'success' })
    setTimeout(() => setCopied(false), 2200)
  }

  // Print recipe
  const handlePrint = () => {
    window.print()
  }

  // Generate another recipe (go to preferences with ingredients retained)
  const handleGenerateAnother = () => {
    navigate('/detect', {
      state: {
        confirmedIngredients,
        preferences,
        step: 2,
      },
    })
  }

  // Modify ingredients (go back to ingredients scanner with ingredients retained)
  const handleModifyIngredients = () => {
    navigate('/detect', {
      state: {
        confirmedIngredients,
        preferences,
        step: 1,
      },
    })
  }

  const hasSubs = recipe?.substitutions?.length > 0
  const hasShop = recipe?.shopping_list?.length > 0
  const tabs = [
    { id: 'steps', label: 'Steps', icon: BookOpen, count: recipe?.instructions?.length || 0 },
    ...(hasShop ? [{ id: 'shopping', label: 'Shopping', icon: ShoppingBag, count: recipe.shopping_list.length }] : []),
    ...(hasSubs ? [{ id: 'swaps', label: 'Swaps', icon: Sparkles, count: recipe.substitutions.length }] : []),
  ]
  const activeTab = tabs.some((t) => t.id === tab) ? tab : 'steps'
  const chipCls = 'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-white/20 text-white text-xs font-bold'
  const btnCls = 'inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-bold text-stone-700 bg-white border border-stone-300 hover:bg-stone-50 transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-stone-400'

  return (
    <div className="print-page py-6 sm:py-8 px-4 sm:px-6 lg:px-8 max-w-6xl mx-auto space-y-4">

      {/* TOP BAR: back + actions */}
      <div className="no-print flex flex-wrap items-center justify-between gap-3">
        <button
          onClick={handleModifyIngredients}
          className="inline-flex items-center gap-2 text-sm font-semibold text-stone-600 hover:text-orange-600 transition-colors cursor-pointer"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Ingredients</span>
        </button>

        <div className="flex flex-wrap items-center gap-2">
          {recipePayload.savedId && (
            <button
              type="button"
              onClick={handleToggleFavorite}
              className={`${btnCls} ${isFavorite ? '!bg-rose-50 !text-rose-600 !border-rose-200' : ''}`}
              aria-label={isFavorite ? 'Remove from Favorites' : 'Add to Favorites'}
            >
              <Heart className={`w-3.5 h-3.5 ${isFavorite ? 'fill-rose-500 text-rose-500' : 'text-stone-500'}`} />
              <span>{isFavorite ? 'Favorited' : 'Favorite'}</span>
            </button>
          )}
          <button type="button" onClick={handleCopyRecipe} className={btnCls}>
            {copied ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5 text-stone-500" />}
            <span>{copied ? 'Copied' : 'Copy'}</span>
          </button>
          <button type="button" onClick={handlePrint} className={btnCls}>
            <Printer className="w-3.5 h-3.5 text-stone-500" />
            <span>Print</span>
          </button>
          <button
            type="button"
            onClick={handleGenerateAnother}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-extrabold text-white bg-gradient-to-r from-orange-500 to-amber-600 hover:from-orange-600 hover:to-amber-700 shadow-md shadow-orange-500/25 transition-all cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange-500 focus-visible:ring-offset-2"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            <span>New recipe</span>
          </button>
        </div>
      </div>

      {/* PRINT-ONLY BRAND HEADER */}
      <div className="print-only pb-4 mb-4 border-b-2 border-stone-900">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-black tracking-tight text-stone-900">
            Dish<span className="text-orange-600">Genie</span>
          </h1>
          <p className="text-xs text-stone-500">Printed: {new Date().toLocaleDateString()}</p>
        </div>
      </div>

      {recipe ? (
        <>
          {/* COMPACT HERO */}
          <div className="rounded-3xl bg-gradient-to-r from-orange-500 via-amber-500 to-orange-600 px-6 py-5 sm:px-8 sm:py-6 text-white shadow-lg shadow-orange-500/15">
            <h1 className="text-2xl sm:text-3xl font-black tracking-tight break-words">
              {cleanText(recipe.name)}
            </h1>
            {recipe.description && recipe.description.trim() && (
              <p className="mt-1.5 text-sm sm:text-base text-orange-50 max-w-3xl leading-snug line-clamp-2">
                {cleanText(recipe.description)}
              </p>
            )}
            <div className="mt-4 flex flex-wrap gap-2">
              <span className={chipCls}><Clock className="w-3.5 h-3.5" />{preferences?.cookingTime || 30} min</span>
              <span className={chipCls}><Flame className="w-3.5 h-3.5" />{preferences?.difficulty || 'Easy'}</span>
              <span className={chipCls}><Users className="w-3.5 h-3.5" />{preferences?.servings || 2} serving{Number(preferences?.servings) === 1 ? '' : 's'}</span>
              <span className={chipCls}><Utensils className="w-3.5 h-3.5" />{preferences?.cuisine || 'Indian'}</span>
              <span className={chipCls}><ChefHat className="w-3.5 h-3.5" />{preferences?.diet || 'Vegetarian'}</span>
              {recipePayload.selectedDish && (
                <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-amber-300 text-stone-900 text-xs font-extrabold">
                  <Sparkles className="w-3.5 h-3.5" />Style: {recipePayload.selectedDish}
                </span>
              )}
            </div>
          </div>

          {/* BODY: ingredients | tabbed scroll panel (fixed height on desktop, content scrolls inside) */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 lg:items-start print:block">

            {/* INGREDIENTS */}
            <section className="lg:col-span-4 flex flex-col min-h-0 max-h-[50vh] lg:max-h-[calc(100vh-19rem)] bg-white rounded-3xl border border-stone-200 shadow-sm print:max-h-none">
              <header className="flex items-center justify-between px-5 py-3.5 border-b border-stone-100 shrink-0">
                <h2 className="flex items-center gap-2 text-base font-extrabold text-stone-900">
                  <span className="w-7 h-7 rounded-lg bg-orange-100 text-orange-600 flex items-center justify-center"><ChefHat className="w-4 h-4" /></span>
                  Ingredients
                </h2>
                <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-stone-100 text-stone-600">
                  {recipe.ingredients?.length || 0}
                </span>
              </header>
              <ul className="flex-1 overflow-y-auto px-5 py-3 space-y-1 print:overflow-visible">
                {recipe.ingredients?.length > 0 ? (
                  recipe.ingredients.map((item, idx) => (
                    <li key={idx} className="flex items-start gap-3 py-2 border-b border-stone-100 last:border-0 text-sm font-medium text-stone-800">
                      <span className="mt-1.5 w-2 h-2 rounded-full bg-orange-500 shrink-0" />
                      <span className="break-words">{cleanText(item)}</span>
                    </li>
                  ))
                ) : (
                  <li className="text-sm text-stone-500 italic py-2">No ingredients specified.</li>
                )}
              </ul>
            </section>

            {/* TABBED PANEL */}
            <section className="lg:col-span-8 flex flex-col min-h-0 max-h-[75vh] lg:max-h-[calc(100vh-19rem)] bg-white rounded-3xl border border-stone-200 shadow-sm print:max-h-none print:mt-6">
              <div role="tablist" aria-label="Recipe sections" className="no-print flex gap-1 px-3 pt-3 border-b border-stone-100 shrink-0">
                {tabs.map(({ id, label, icon: Icon, count }) => (
                  <button
                    key={id}
                    role="tab"
                    id={`tab-${id}`}
                    aria-selected={activeTab === id}
                    aria-controls={`panel-${id}`}
                    type="button"
                    onClick={() => setTab(id)}
                    className={`inline-flex items-center gap-2 px-4 py-2.5 rounded-t-xl text-sm font-bold border-b-2 -mb-px transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange-400 ${
                      activeTab === id
                        ? 'border-orange-500 text-orange-700 bg-orange-50/60'
                        : 'border-transparent text-stone-500 hover:text-stone-800'
                    }`}
                  >
                    <Icon className="w-4 h-4" aria-hidden="true" />
                    {label}
                    <span className="text-[11px] font-semibold px-1.5 py-0.5 rounded-full bg-stone-100 text-stone-600">{count}</span>
                  </button>
                ))}
              </div>

              <div className="flex-1 min-h-0 overflow-y-auto px-5 py-4 print:overflow-visible">
                {/* STEPS */}
                <div id="panel-steps" role="tabpanel" aria-labelledby="tab-steps" className={activeTab === 'steps' ? '' : 'hidden print:block'}>
                  {recipe.instructions?.length > 0 ? (
                    <ol className="space-y-3">
                      {recipe.instructions.map((step, idx) => (
                        <li key={idx} className="flex items-start gap-3.5">
                          <span className="w-8 h-8 rounded-lg bg-gradient-to-br from-orange-500 to-amber-600 text-white font-mono text-xs font-black flex items-center justify-center shrink-0">
                            {idx + 1}
                          </span>
                          <p className="pt-1 text-sm sm:text-[15px] text-stone-800 leading-relaxed">{cleanText(step)}</p>
                        </li>
                      ))}
                    </ol>
                  ) : (
                    <p className="text-sm text-stone-500 italic">No cooking instructions provided.</p>
                  )}
                </div>

                {/* SHOPPING */}
                {hasShop && (
                  <div id="panel-shopping" role="tabpanel" aria-labelledby="tab-shopping" className={activeTab === 'shopping' ? '' : 'hidden print:block print:mt-6'}>
                    <div className="flex items-center justify-between mb-2">
                      <h3 className="hidden print:block text-base font-extrabold text-stone-900">Shopping List</h3>
                      {Object.values(checkedItems).some(Boolean) && (
                        <button type="button" onClick={handleClearCompleted} className="no-print ml-auto text-xs font-semibold text-stone-500 hover:text-stone-800 underline underline-offset-2 cursor-pointer">
                          Clear completed
                        </button>
                      )}
                    </div>
                    <ul className="grid sm:grid-cols-2 gap-2">
                      {recipe.shopping_list.map((item, idx) => {
                        const isChecked = !!checkedItems[idx]
                        return (
                          <li key={idx}>
                            <button
                              type="button"
                              onClick={() => toggleShoppingItem(idx)}
                              aria-pressed={isChecked}
                              className={`w-full flex items-center gap-3 p-3 rounded-xl border text-left transition-colors cursor-pointer ${
                                isChecked ? 'bg-emerald-50/50 border-emerald-200' : 'bg-stone-50 border-stone-200 hover:border-emerald-300'
                              }`}
                            >
                              {isChecked ? <CheckSquare className="w-5 h-5 text-emerald-600 shrink-0" /> : <Square className="w-5 h-5 text-stone-300 shrink-0" />}
                              <span className={`text-sm font-medium ${isChecked ? 'line-through text-stone-400' : 'text-stone-800'}`}>{cleanText(item)}</span>
                            </button>
                          </li>
                        )
                      })}
                    </ul>
                  </div>
                )}

                {/* SWAPS */}
                {hasSubs && (
                  <div id="panel-swaps" role="tabpanel" aria-labelledby="tab-swaps" className={activeTab === 'swaps' ? '' : 'hidden print:block print:mt-6'}>
                    <h3 className="hidden print:block text-base font-extrabold text-stone-900 mb-2">Possible Substitutions</h3>
                    <ul className="grid sm:grid-cols-2 gap-3">
                      {recipe.substitutions.map((sub, idx) => (
                        <li key={idx} className="p-4 rounded-xl bg-amber-50/70 border border-amber-200/80 text-sm">
                          <p className="font-bold text-amber-900">{cleanText(sub.ingredient)}</p>
                          <p className="mt-1 text-stone-800"><span className="text-amber-500 font-bold">→ </span>{cleanText(sub.replacement)}</p>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </section>
          </div>
        </>
      ) : (
        /* Raw model text fallback when no structured recipe exists */
        <div className="bg-white rounded-3xl p-6 sm:p-8 border border-stone-200 shadow-sm space-y-4">
          <div className="flex items-center gap-3 pb-3 border-b border-stone-100">
            <div className="w-10 h-10 rounded-xl bg-amber-50 border border-amber-200 flex items-center justify-center text-amber-600">
              <AlertCircle className="w-5 h-5" />
            </div>
            <h2 className="text-xl font-extrabold text-stone-900">Generated Recipe</h2>
          </div>
          <div className="p-5 rounded-2xl bg-stone-50 border border-stone-200 text-sm sm:text-base text-stone-800 leading-relaxed whitespace-pre-wrap">
            {raw_text || 'No recipe text generated.'}
          </div>
        </div>
      )}

      {toast && (
        <Toast
          message={toast.text}
          type={toast.type}
          onClose={() => setToast(null)}
        />
      )}
    </div>
  )
}
