import { useState } from 'react'
import { Search, Check, X } from 'lucide-react'
import {
  INGREDIENT_CLASSES,
  INGREDIENT_EMOJIS,
  formatIngredientName,
} from '../services/api'

export default function IngredientSelector({
  currentSelection,
  onSelect,
  onCancel,
}) {
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedClass, setSelectedClass] = useState(
    currentSelection || INGREDIENT_CLASSES[0]
  )

  const filteredClasses = INGREDIENT_CLASSES.filter((cls) =>
    formatIngredientName(cls).toLowerCase().includes(searchQuery.toLowerCase())
  )

  const handleApply = () => {
    if (selectedClass) {
      onSelect(selectedClass)
    }
  }

  return (
    <div className="p-4 sm:p-5 rounded-2xl bg-white border border-stone-200 shadow-md space-y-4 animate-in fade-in zoom-in-95 duration-200">
      <div className="flex items-center justify-between">
        <div>
          <h4 className="text-sm font-bold text-stone-900">
            Select an ingredient from 247 categories
          </h4>
          <p className="text-xs text-stone-500">
            Choose the correct produce or ingredient category identified in your pantry
          </p>
        </div>
        {onCancel && (
          <button
            type="button"
            onClick={onCancel}
            className="p-1 rounded-lg text-stone-400 hover:text-stone-700"
            aria-label="Cancel selection"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* Search Input */}
      <div className="relative">
        <Search className="w-4 h-4 text-stone-400 absolute left-3 top-1/2 -translate-y-1/2" aria-hidden="true" />
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="Search ingredients (e.g. Tomato, Garlic, Mushroom)..."
          aria-label="Search vegetables"
          className="w-full pl-9 pr-4 py-2 bg-stone-50 border border-stone-200 rounded-xl text-xs sm:text-sm text-stone-800 focus:outline-hidden focus:ring-2 focus:ring-orange-500"
        />
      </div>

      {/* Grid of options */}
      <div className="max-h-48 overflow-y-auto grid grid-cols-2 sm:grid-cols-3 gap-2 pr-1">
        {filteredClasses.map((cls) => {
          const isSelected = selectedClass === cls
          return (
            <button
              key={cls}
              type="button"
              onClick={() => setSelectedClass(cls)}
              className={`flex items-center gap-2 p-2.5 rounded-xl text-xs font-semibold text-left transition-all cursor-pointer ${
                isSelected
                  ? 'bg-orange-500 text-white shadow-xs'
                  : 'bg-stone-50 text-stone-700 hover:bg-stone-100 border border-stone-200/60'
              }`}
            >
              <span className="text-base">{INGREDIENT_EMOJIS[cls] || '🥗'}</span>
              <span className="truncate flex-1">{formatIngredientName(cls)}</span>
              {isSelected && <Check className="w-3.5 h-3.5 shrink-0" />}
            </button>
          )
        })}
        {filteredClasses.length === 0 && (
          <div className="col-span-full py-4 text-center text-xs text-stone-400">
            No matching ingredient class found.
          </div>
        )}
      </div>

      {/* Action Buttons */}
      <div className="pt-2 border-t border-stone-100 flex items-center justify-end gap-2.5">
        {onCancel && (
          <button
            type="button"
            onClick={onCancel}
            className="px-4 py-2 rounded-xl text-xs font-semibold text-stone-600 hover:text-stone-800 bg-stone-100 hover:bg-stone-200 transition-colors cursor-pointer"
          >
            Cancel
          </button>
        )}
        <button
          type="button"
          onClick={handleApply}
          className="inline-flex items-center gap-1.5 px-5 py-2 rounded-xl text-xs font-bold text-white bg-orange-600 hover:bg-orange-700 shadow-xs transition-colors cursor-pointer"
        >
          <Check className="w-3.5 h-3.5" />
          <span>Apply Selection</span>
        </button>
      </div>
    </div>
  )
}
