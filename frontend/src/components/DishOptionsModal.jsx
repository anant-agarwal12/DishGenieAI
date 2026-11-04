import React from 'react'
import {
  ChefHat,
  Clock,
  Sparkles,
  ArrowRight,
  X,
  Flame,
  Check,
  Compass,
} from 'lucide-react'

export default function DishOptionsModal({
  isOpen,
  onClose,
  options = [],
  onSelectOption,
  onAutoGenerate,
  isGenerating = false,
  selectedDishName = null,
}) {
  if (!isOpen) return null

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="dish-options-title"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 bg-stone-900/60 backdrop-blur-sm animate-fade-in"
    >
      <div className="relative w-full max-w-3xl bg-white rounded-3xl shadow-2xl border border-stone-200 overflow-hidden flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="px-6 sm:px-8 py-5 border-b border-stone-100 bg-gradient-to-r from-orange-50/60 via-amber-50/30 to-white flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-2xl bg-orange-500/10 text-orange-600 flex items-center justify-center border border-orange-500/20">
              <ChefHat className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold tracking-wider text-orange-600 uppercase">
                  Interactive Recipe Selection
                </span>
                <span className="text-[10px] bg-orange-100 text-orange-800 font-bold px-2 py-0.5 rounded-full">
                  Step 2 of 2
                </span>
              </div>
              <h2
                id="dish-options-title"
                className="text-xl sm:text-2xl font-extrabold text-stone-900 tracking-tight"
              >
                Choose Your Dish Style
              </h2>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={isGenerating}
            className="p-2 rounded-full text-stone-400 hover:text-stone-700 hover:bg-stone-100 transition-colors focus:outline-none focus:ring-2 focus:ring-orange-500"
            aria-label="Close selection modal"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content Body */}
        <div className="p-6 sm:p-8 overflow-y-auto space-y-4">
          <p className="text-sm text-stone-600 leading-relaxed">
            DishGenie discovered 3 authentic culinary styles tailored to your pantry. Click your preferred dish to synthesize the complete personalized recipe and shopping list:
          </p>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-2">
            {options.map((opt, idx) => {
              const isSelected = selectedDishName === opt.name
              return (
                <div
                  key={opt.name || idx}
                  onClick={() => !isGenerating && onSelectOption(opt)}
                  className={`group relative p-5 rounded-2xl border transition-all duration-200 cursor-pointer flex flex-col justify-between text-left ${
                    isSelected
                      ? 'border-orange-500 bg-orange-50/40 shadow-md ring-2 ring-orange-400/40'
                      : 'border-stone-200 bg-stone-50/50 hover:bg-white hover:border-orange-300 hover:shadow-lg hover:-translate-y-0.5'
                  }`}
                >
                  <div>
                    {/* Option Tag */}
                    <div className="flex items-center justify-between gap-2 mb-2.5">
                      <span className="text-[11px] font-bold tracking-wider uppercase px-2 py-0.5 rounded-md bg-stone-200/80 text-stone-700 group-hover:bg-orange-100 group-hover:text-orange-800 transition-colors">
                        Option {idx + 1}
                      </span>
                      <span className="text-xs font-medium text-stone-500 flex items-center gap-1">
                        <Clock className="w-3.5 h-3.5 text-stone-400" />
                        {opt.cooking_time || 30}m
                      </span>
                    </div>

                    {/* Dish Title */}
                    <h3 className="text-base font-bold text-stone-900 group-hover:text-orange-600 transition-colors leading-snug line-clamp-2">
                      {opt.name}
                    </h3>

                    {/* Short Description */}
                    <p className="mt-2 text-xs text-stone-600 line-clamp-3 leading-relaxed">
                      {opt.description || 'Authentic homestyle preparation tailored to your confirmed pantry ingredients.'}
                    </p>
                  </div>

                  <div className="pt-4 mt-4 border-t border-stone-200/60 flex items-center justify-between">
                    <span className="text-[11px] font-medium text-stone-500">
                      {opt.cuisine || 'Indian'} • {opt.diet || 'Vegetarian'}
                    </span>
                    <button
                      type="button"
                      disabled={isGenerating}
                      className="inline-flex items-center gap-1 text-xs font-semibold text-orange-600 group-hover:text-orange-700"
                    >
                      <span>Cook</span>
                      <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" />
                    </button>
                  </div>
                </div>
              )
            })}
          </div>

          {/* Fallback note if no options returned */}
          {options.length === 0 && (
            <div className="text-center py-8 text-stone-500">
              <Compass className="w-8 h-8 text-stone-400 mx-auto mb-2 animate-spin" />
              <p className="text-sm font-medium">Retrieving matching candidate styles from culinary index...</p>
            </div>
          )}
        </div>

        {/* Footer Actions */}
        <div className="px-6 sm:px-8 py-4 bg-stone-50 border-t border-stone-200/80 flex flex-col sm:flex-row items-center justify-between gap-3">
          <p className="text-xs text-stone-500 hidden sm:block">
            DishGenie Local Generative AI • Stovetop & Pantry Optimized
          </p>

          <div className="flex items-center gap-3 w-full sm:w-auto justify-end">
            <button
              type="button"
              onClick={onAutoGenerate}
              disabled={isGenerating}
              className="w-full sm:w-auto px-4 py-2 text-xs font-semibold text-stone-700 bg-white border border-stone-300 rounded-xl hover:bg-stone-100 transition-colors shadow-xs"
            >
              Surprise Me (Auto-Select)
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
