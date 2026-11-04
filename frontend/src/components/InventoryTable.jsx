import { useState } from 'react'
import {
  AlertTriangle,
  Clock,
  Plus,
  Minus,
  Trash2,
  Layers,
} from 'lucide-react'
import { INGREDIENT_EMOJIS, formatIngredientName } from '../services/api'
import IngredientSelector from './IngredientSelector'

export default function InventoryTable({
  inventory = [],
  onUpdateInventory,
  onRemoveItem,
  onAddItem,
}) {
  const [showAddPicker, setShowAddPicker] = useState(false)

  const handleCountChange = (index, delta) => {
    const updated = [...inventory]
    const current = updated[index].count || 1
    const nextCount = Math.max(1, current + delta)
    updated[index] = { ...updated[index], count: nextCount }
    onUpdateInventory(updated)
  }

  const handleExpiryChange = (index, newDays) => {
    const days = Math.max(1, parseInt(newDays) || 1)
    const updated = [...inventory]
    let status = 'Fresh'
    if (days <= 3) status = 'Use First'
    else if (days <= 7) status = 'Medium'

    updated[index] = {
      ...updated[index],
      min_expiry_days: days,
      status: status,
    }
    onUpdateInventory(updated)
  }

  const useFirstCount = inventory.filter(
    (item) => item.status === 'Use First' || item.min_expiry_days <= 3
  ).length

  return (
    <div className="bg-white rounded-3xl p-6 sm:p-8 border border-stone-200 shadow-xl shadow-stone-900/5 space-y-6">
      
      {/* Header & Badges */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-stone-100">
        <div>
          <div className="flex items-center gap-2">
            <Layers className="w-5 h-5 text-orange-600" />
            <h3 className="text-lg font-extrabold text-stone-900">
              Produce Inventory & Freshness Tracking
            </h3>
          </div>
          <p className="text-xs text-stone-500 mt-1">
            Two-stage instance localization and deterministic freshness grading
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span className="px-3 py-1 rounded-full bg-stone-100 text-stone-700 font-mono text-xs font-bold">
            {inventory.reduce((sum, item) => sum + (item.count || 1), 0)} Total Units
          </span>
          <button
            type="button"
            onClick={() => setShowAddPicker(true)}
            className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-full text-xs font-bold text-orange-800 bg-orange-100/70 hover:bg-orange-200 border border-orange-200 transition-colors cursor-pointer"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>Add Item</span>
          </button>
        </div>
      </div>

      {/* Food Waste Alert if any item is USE FIRST */}
      {useFirstCount > 0 && (
        <div className="flex items-start gap-3 p-4 rounded-2xl bg-rose-50 border border-rose-200 text-rose-900 text-xs animate-in fade-in duration-200">
          <AlertTriangle className="w-5 h-5 text-rose-600 shrink-0 mt-0.5" />
          <div className="space-y-0.5">
            <span className="font-bold text-rose-950">
              Food Waste Alert: {useFirstCount} item{useFirstCount > 1 ? 's' : ''} expiring soon!
            </span>
            <p className="text-rose-700">
              DishGenie will prioritize your expiring ingredients in the recipe instructions to prevent food waste.
            </p>
          </div>
        </div>
      )}

      {/* Manual Add Picker Modal / Inline View */}
      {showAddPicker && (
        <div className="p-4 rounded-2xl bg-stone-50 border border-stone-200 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-stone-700 uppercase tracking-wider">
              Add Produce to Inventory
            </span>
            <button
              type="button"
              onClick={() => setShowAddPicker(false)}
              className="text-xs text-stone-500 hover:text-stone-800"
            >
              Cancel
            </button>
          </div>
          <IngredientSelector
            onSelect={(selectedClass) => {
              onAddItem(selectedClass)
              setShowAddPicker(false)
            }}
            onCancel={() => setShowAddPicker(false)}
          />
        </div>
      )}

      {/* Inventory Table List */}
      <div className="divide-y divide-stone-100 overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="text-[11px] font-bold uppercase tracking-wider text-stone-500 border-b border-stone-200">
              <th className="py-2.5 px-3">Ingredient</th>
              <th className="py-2.5 px-3 text-center">Count</th>
              <th className="py-2.5 px-3">Freshness State</th>
              <th className="py-2.5 px-3">Est. Expiry</th>
              <th className="py-2.5 px-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-stone-100">
            {inventory.map((item, idx) => {
              const status = item.status || 'Fresh'
              const isUseFirst = status === 'Use First' || (item.min_expiry_days && item.min_expiry_days <= 3)

              let badgeColor = 'bg-emerald-50 text-emerald-800 border-emerald-200'
              if (isUseFirst) {
                badgeColor = 'bg-rose-50 text-rose-800 border-rose-200 font-bold'
              } else if (status === 'Medium') {
                badgeColor = 'bg-amber-50 text-amber-800 border-amber-200 font-bold'
              }

              return (
                <tr key={idx} className="hover:bg-stone-50/70 transition-colors">
                  {/* Ingredient Name */}
                  <td className="py-3.5 px-3">
                    <div className="flex items-center gap-2.5">
                      <span className="text-2xl shrink-0">
                        {INGREDIENT_EMOJIS[item.ingredient] || '🥗'}
                      </span>
                      <div>
                        <p className="font-extrabold text-stone-900 text-sm">
                          {formatIngredientName(item.ingredient)}
                        </p>
                        <p className="text-[10px] text-stone-400 font-mono">
                          {item.ingredient}
                        </p>
                      </div>
                    </div>
                  </td>

                  {/* Quantity Counter */}
                  <td className="py-3.5 px-3">
                    <div className="flex items-center justify-center gap-1.5 bg-stone-100 rounded-xl p-1 max-w-[100px] mx-auto">
                      <button
                        type="button"
                        onClick={() => handleCountChange(idx, -1)}
                        className="w-6 h-6 rounded-lg bg-white hover:bg-stone-200 text-stone-700 flex items-center justify-center text-xs font-bold transition-colors cursor-pointer shadow-2xs"
                        aria-label="Decrease quantity"
                      >
                        <Minus className="w-3 h-3" />
                      </button>
                      <span className="w-7 text-center font-mono font-black text-stone-900 text-sm">
                        {item.count || 1}
                      </span>
                      <button
                        type="button"
                        onClick={() => handleCountChange(idx, 1)}
                        className="w-6 h-6 rounded-lg bg-white hover:bg-stone-200 text-stone-700 flex items-center justify-center text-xs font-bold transition-colors cursor-pointer shadow-2xs"
                        aria-label="Increase quantity"
                      >
                        <Plus className="w-3 h-3" />
                      </button>
                    </div>
                  </td>

                  {/* Freshness Badge */}
                  <td className="py-3.5 px-3">
                    <span
                      className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs border ${badgeColor}`}
                    >
                      {isUseFirst && <span className="w-2 h-2 rounded-full bg-rose-600 animate-pulse"></span>}
                      <span>{isUseFirst ? 'USE FIRST' : status}</span>
                    </span>
                  </td>

                  {/* Estimated Expiry Days Input */}
                  <td className="py-3.5 px-3">
                    <div className="flex items-center gap-1.5 text-xs text-stone-700 font-semibold">
                      <Clock className="w-3.5 h-3.5 text-stone-400 shrink-0" />
                      <input
                        type="number"
                        min="1"
                        max="365"
                        value={item.min_expiry_days || 7}
                        onChange={(e) => handleExpiryChange(idx, e.target.value)}
                        className="w-14 px-2 py-1 text-center font-mono font-bold text-xs rounded-lg border border-stone-200 bg-white focus:outline-none focus:ring-1 focus:ring-orange-500"
                        aria-label="Estimated expiry days"
                      />
                      <span className="text-stone-500">days</span>
                    </div>
                  </td>

                  {/* Remove Button */}
                  <td className="py-3.5 px-3 text-right">
                    <button
                      type="button"
                      onClick={() => onRemoveItem(item.ingredient)}
                      className="p-1.5 rounded-lg text-stone-400 hover:text-rose-600 hover:bg-rose-50 transition-colors cursor-pointer"
                      title="Remove item from inventory"
                      aria-label="Remove item"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

    </div>
  )
}
