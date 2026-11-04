import { useState, useRef, useEffect } from 'react'
import { Link, useNavigate, useLocation } from 'react-router-dom'
import {
  UploadCloud,
  FileImage,
  Trash2,
  Sparkles,
  Loader2,
  AlertCircle,
  ArrowLeft,
  Check,
  RefreshCw,
  RotateCcw,
  Eye,
  EyeOff,
  Boxes,
} from 'lucide-react'
import {
  predictIngredient,
  generateRecipe,
  fetchRecipeCandidates,
  INGREDIENT_EMOJIS,
  formatIngredientName,
} from '../services/api'
import IngredientList from '../components/IngredientList'
import IngredientSelector from '../components/IngredientSelector'
import InventoryTable from '../components/InventoryTable'
import RecipePreferences from '../components/RecipePreferences'
import RecipeRequestModal from '../components/RecipeRequestModal'
import DishOptionsModal from '../components/DishOptionsModal'
import LoadingState from '../components/LoadingState'
import Toast from '../components/Toast'
import { saveRecipeToHistory } from '../services/storage'

export default function Detect() {
  const navigate = useNavigate()
  const location = useLocation()

  const fileInputRef = useRef(null)
  const uploadAreaRef = useRef(null)
  const preferencesRef = useRef(null)

  // MULTIPLE confirmed ingredients list (persisted in sessionStorage)
  const [confirmedIngredients, setConfirmedIngredients] = useState(() => {
    if (location.state?.confirmedIngredients) {
      return location.state.confirmedIngredients
    }
    try {
      const cached = sessionStorage.getItem('dishgenie_confirmed_ingredients')
      return cached ? JSON.parse(cached) : []
    } catch {
      return []
    }
  })

  // Current active upload & prediction session state
  const [selectedImage, setSelectedImage] = useState(null)
  const [previewUrl, setPreviewUrl] = useState(null)
  const [isPredicting, setIsPredicting] = useState(false)
  const [prediction, setPrediction] = useState(null)
  const [topPredictions, setTopPredictions] = useState(null)
  const [inventory, setInventory] = useState([])
  const [detections, setDetections] = useState([])
  const [annotatedImage, setAnnotatedImage] = useState(null)
  const [showAnnotated, setShowAnnotated] = useState(true)
  const [totalDetectedItems, setTotalDetectedItems] = useState(0)
  const [error, setError] = useState(null)
  const [predictionFailed, setPredictionFailed] = useState(false)
  const [preferenceErrors, setPreferenceErrors] = useState({})
  const [toast, setToast] = useState(null)

  // UI modal / picker states
  const [dragActive, setDragActive] = useState(false)
  const [isChanging, setIsChanging] = useState(false)
  const [showManualPicker, setShowManualPicker] = useState(false)

  // Structured Recipe Preferences (persisted in sessionStorage)
  const [preferences, setPreferences] = useState(() => {
    if (location.state?.preferences) {
      return location.state.preferences
    }
    try {
      const cached = sessionStorage.getItem('dishgenie_preferences')
      if (cached) return JSON.parse(cached)
    } catch {
      // default
    }
    return {
      diet: 'Vegetarian',
      cuisine: 'Indian',
      cookingTime: 30,
      difficulty: 'Easy',
      servings: 2,
      additionalIngredients: '',
    }
  })

  // Final compiled request payload & Generated Recipe state
  const [recipeRequestPayload, setRecipeRequestPayload] = useState(null)
  const [showPayloadModal, setShowPayloadModal] = useState(false)
  const [isGeneratingRecipe, setIsGeneratingRecipe] = useState(false)
  const [generationError, setGenerationError] = useState(false)

  // Interactive Recipe Selection Flow ("Choose Your Dish Option")
  const [dishOptions, setDishOptions] = useState([])
  const [showOptionsModal, setShowOptionsModal] = useState(false)
  const [selectedDishName, setSelectedDishName] = useState(null)
  const [isLoadingCandidates, setIsLoadingCandidates] = useState(false)

  // Rotating UI feedback messages during generation
  const loadingStages = [
    'Analyzing your ingredients',
    'Personalizing your recipe',
    'Preparing cooking instructions',
  ]
  const [currentLoadingStage, setCurrentLoadingStage] = useState(0)

  useEffect(() => {
    let interval
    if (isGeneratingRecipe) {
      setCurrentLoadingStage(0)
      interval = setInterval(() => {
        setCurrentLoadingStage((prev) => (prev + 1) % 3)
      }, 1800)
    }
    return () => {
      if (interval) clearInterval(interval)
    }
  }, [isGeneratingRecipe])

  // Persist confirmed ingredients across refreshes
  useEffect(() => {
    if (confirmedIngredients.length > 0) {
      sessionStorage.setItem(
        'dishgenie_confirmed_ingredients',
        JSON.stringify(confirmedIngredients)
      )
    } else {
      sessionStorage.removeItem('dishgenie_confirmed_ingredients')
    }
  }, [confirmedIngredients])

  // Persist preferences across refreshes
  useEffect(() => {
    sessionStorage.setItem('dishgenie_preferences', JSON.stringify(preferences))
  }, [preferences])

  // Restore state if returning from Recipe page
  useEffect(() => {
    if (location.state?.confirmedIngredients) {
      setConfirmedIngredients(location.state.confirmedIngredients)
    }
    if (location.state?.preferences) {
      setPreferences(location.state.preferences)
    }
    if (location.state?.step === 2) {
      setTimeout(() => {
        preferencesRef.current?.scrollIntoView({ behavior: 'smooth' })
      }, 150)
    }
  }, [location.state])

  // Clean up object URLs on unmount or file change
  useEffect(() => {
    return () => {
      if (previewUrl) {
        URL.revokeObjectURL(previewUrl)
      }
    }
  }, [previewUrl])

  // Handle incoming file
  const handleFileProcess = (file) => {
    if (!file) return

    const validTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/webp']
    if (!validTypes.includes(file.type.toLowerCase())) {
      setError('Please upload a valid image file (JPG, JPEG, or PNG).')
      setPredictionFailed(true)
      return
    }

    const MAX_SIZE = 10 * 1024 * 1024 // 10MB
    if (file.size > MAX_SIZE) {
      setError('Image file is too large. Please select an image under 10MB.')
      setPredictionFailed(true)
      return
    }

    if (previewUrl) {
      URL.revokeObjectURL(previewUrl)
    }

    setError(null)
    setPredictionFailed(false)
    setPrediction(null)
    setTopPredictions(null)
    setIsChanging(false)

    setSelectedImage(file)
    setPreviewUrl(URL.createObjectURL(file))
  }

  const handleInputChange = (e) => {
    const file = e.target.files?.[0]
    if (file) {
      handleFileProcess(file)
    }
  }

  // Drag and drop handlers
  const handleDragEnter = (e) => {
    e.preventDefault()
    e.stopPropagation()
    if (!isPredicting) setDragActive(true)
  }

  const handleDragLeave = (e) => {
    e.preventDefault()
    e.stopPropagation()
    setDragActive(false)
  }

  const handleDragOver = (e) => {
    e.preventDefault()
    e.stopPropagation()
  }

  const handleDrop = (e) => {
    e.preventDefault()
    e.stopPropagation()
    setDragActive(false)
    if (isPredicting) return
    const file = e.dataTransfer.files?.[0]
    if (file) {
      handleFileProcess(file)
    }
  }

  // Clear current upload slot
  const handleClearCurrentSlot = () => {
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl)
    }
    setSelectedImage(null)
    setPreviewUrl(null)
    setPrediction(null)
    setTopPredictions(null)
    setAnnotatedImage(null)
    setDetections([])
    setTotalDetectedItems(0)
    setError(null)
    setPredictionFailed(false)
    setIsChanging(false)
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  // Trigger CNN inference on selected image
  const handleDetect = async () => {
    if (!selectedImage) {
      setError('Please select an image file to analyze.')
      return
    }
    if (isPredicting) return

    setIsPredicting(true)
    setError(null)
    setPredictionFailed(false)

    try {
      const result = await predictIngredient(selectedImage)
      setPrediction(result.prediction)
      setTopPredictions(result.top_predictions)
      setAnnotatedImage(result.annotated_image || null)
      setDetections(result.detections || [])
      setTotalDetectedItems(result.total_items_detected || 1)

      const inv = (result.inventory && result.inventory.length > 0)
        ? result.inventory
        : [{
            ingredient: result.prediction.name,
            count: 1,
            min_expiry_days: 7,
            status: 'Fresh'
          }]
      setInventory(inv)

      // Auto-populate confirmedIngredients from detected inventory
      const detectedClasses = inv.map((item) => item.ingredient)
      setConfirmedIngredients((prev) => {
        const next = [...prev]
        detectedClasses.forEach((cls) => {
          if (!next.includes(cls)) next.push(cls)
        })
        return next
      })
    } catch (err) {
      setPredictionFailed(true)
      setError(err.message || "We couldn't analyze this image.")
    } finally {
      setIsPredicting(false)
    }
  }

  // Inventory table actions
  const handleUpdateInventory = (newInventory) => {
    setInventory(newInventory)
    const activeNames = newInventory.map((i) => i.ingredient)
    setConfirmedIngredients((prev) => {
      const next = [...prev]
      activeNames.forEach((name) => {
        if (!next.includes(name)) next.push(name)
      })
      return next
    })
  }

  const handleRemoveInventoryItem = (nameToRemove) => {
    setInventory((prev) => prev.filter((i) => i.ingredient !== nameToRemove))
    handleRemoveConfirmed(nameToRemove)
  }

  const handleAddInventoryItem = (selectedClass) => {
    if (!selectedClass) return
    setInventory((prev) => {
      const idx = prev.findIndex((i) => i.ingredient === selectedClass)
      if (idx !== -1) {
        const updated = [...prev]
        updated[idx] = { ...updated[idx], count: (updated[idx].count || 1) + 1 }
        return updated
      }
      return [
        ...prev,
        {
          ingredient: selectedClass,
          count: 1,
          min_expiry_days: 7,
          status: 'Fresh',
        },
      ]
    })
    handleConfirmIngredient(selectedClass)
  }

  // Confirm ingredient and append to multiple confirmed ingredients list
  const handleConfirmIngredient = (ingredientName) => {
    if (!ingredientName) return

    // Avoid duplicates
    if (!confirmedIngredients.includes(ingredientName)) {
      setConfirmedIngredients((prev) => [...prev, ingredientName])
      setToast({
        text: `Added ${formatIngredientName(ingredientName)} to confirmed ingredients`,
        type: 'success',
      })
    }

    // Smoothly scroll to preferences section
    setTimeout(() => {
      if (preferencesRef.current) {
        preferencesRef.current.scrollIntoView({ behavior: 'smooth' })
      }
    }, 150)
  }

  // Confirm all detected inventory items and proceed
  const handleConfirmAllInventory = () => {
    if (inventory && inventory.length > 0) {
      const activeNames = inventory.map((i) => i.ingredient)
      setConfirmedIngredients((prev) => {
        const next = [...prev]
        activeNames.forEach((cls) => {
          if (!next.includes(cls)) next.push(cls)
        })
        return next
      })
      setToast({
        text: `Confirmed ${activeNames.length} item(s) for recipe generation!`,
        type: 'success',
      })
    } else if (prediction) {
      handleConfirmIngredient(prediction.name)
    }

    setTimeout(() => {
      if (preferencesRef.current) {
        preferencesRef.current.scrollIntoView({ behavior: 'smooth' })
      }
    }, 150)
  }

  // Remove an ingredient from confirmed list
  const handleRemoveConfirmed = (nameToRemove) => {
    setConfirmedIngredients((prev) =>
      prev.filter((item) => item !== nameToRemove)
    )
    setToast({
      text: `Removed ${formatIngredientName(nameToRemove)}`,
      type: 'success',
    })
  }

  // User clicked "+ Add another ingredient"
  const handleAddAnother = () => {
    handleClearCurrentSlot()
    if (uploadAreaRef.current) {
      uploadAreaRef.current.scrollIntoView({ behavior: 'smooth' })
    }
    // Auto-open file chooser
    setTimeout(() => {
      fileInputRef.current?.click()
    }, 200)
  }

  // Helper to compile the active recipe request payload
  const buildRecipePayload = () => {
    const cookingTimeNum = Number(preferences.cookingTime) || 30
    const servingsNum = Number(preferences.servings) || 2
    return {
      ingredients: [...confirmedIngredients],
      inventory: inventory.length > 0
        ? inventory
        : confirmedIngredients.map((ing) => ({
            ingredient: ing,
            count: 1,
            min_expiry_days: 7,
            status: 'Fresh',
          })),
      preferences: {
        diet: preferences.diet,
        cuisine: preferences.cuisine,
        cookingTime: cookingTimeNum,
        difficulty: preferences.difficulty || 'Easy',
        servings: servingsNum,
        additionalIngredients: (preferences.additionalIngredients || '').trim(),
      },
    }
  }

  // Step A: Trigger Candidate Selection Modal ("Choose Your Dish Option")
  const handleGenerateRecipe = async () => {
    if (isGeneratingRecipe || isLoadingCandidates) return

    // Validate that at least one ingredient is confirmed
    if (!confirmedIngredients || confirmedIngredients.length === 0) {
      setError('Please add at least one ingredient before generating.')
      if (uploadAreaRef.current) {
        uploadAreaRef.current.scrollIntoView({ behavior: 'smooth' })
      }
      return
    }

    // Inline preference validation
    const errs = {}
    if (!preferences.diet || !preferences.diet.trim()) {
      errs.diet = 'Please select a diet preference.'
    }
    if (!preferences.cuisine || !preferences.cuisine.trim()) {
      errs.cuisine = 'Please select a cuisine style.'
    }
    const cookingTimeNum = Number(preferences.cookingTime)
    if (isNaN(cookingTimeNum) || cookingTimeNum <= 0) {
      errs.cookingTime = 'Please specify a valid cooking duration.'
    }
    const servingsNum = Number(preferences.servings)
    if (isNaN(servingsNum) || servingsNum <= 0) {
      errs.servings = 'Please specify a valid portion size.'
    }

    if (Object.keys(errs).length > 0) {
      setPreferenceErrors(errs)
      if (preferencesRef.current) {
        preferencesRef.current.scrollIntoView({ behavior: 'smooth' })
      }
      return
    }

    setPreferenceErrors({})
    setError(null)
    setGenerationError(false)

    // Show the selected ingredients + preferences for review before generating
    setRecipeRequestPayload(buildRecipePayload())
    setShowPayloadModal(true)
  }

  // Step A2: user accepted the review dialog -> fetch dish options
  const proceedToDishOptions = async () => {
    setShowPayloadModal(false)
    const payload = recipeRequestPayload || buildRecipePayload()
    setIsLoadingCandidates(true)

    // Retrieve top 3 matching database candidates
    try {
      const candidatesRes = await fetchRecipeCandidates(payload)
      setIsLoadingCandidates(false)
      if (candidatesRes?.success && candidatesRes.options && candidatesRes.options.length > 0) {
        setDishOptions(candidatesRes.options)
        setShowOptionsModal(true)
      } else {
        // Direct fallback if no candidates returned
        executeRecipeSynthesis(payload)
      }
    } catch (err) {
      console.warn('Could not fetch candidate styles, falling back directly:', err)
      setIsLoadingCandidates(false)
      executeRecipeSynthesis(payload)
    }
  }

  // Step C: Execute Final Neural Synthesis for Selected Dish
  const handleSelectDishOption = (option) => {
    setShowOptionsModal(false)
    const payload = recipeRequestPayload || buildRecipePayload()
    executeRecipeSynthesis({ ...payload, selected_dish: option.name })
  }

  const handleAutoGenerateWithoutDish = () => {
    setShowOptionsModal(false)
    const payload = recipeRequestPayload || buildRecipePayload()
    executeRecipeSynthesis(payload)
  }

  const executeRecipeSynthesis = async (finalPayload) => {
    setIsGeneratingRecipe(true)
    setGenerationError(false)
    setError(null)
    setSelectedDishName(finalPayload.selected_dish || null)

    try {
      const result = await generateRecipe(finalPayload)
      // Save successfully generated recipe to localStorage history
      const savedRecord = saveRecipeToHistory(result, preferences, confirmedIngredients)
      setIsGeneratingRecipe(false)
      // Navigate to dedicated recipe result page with state
      navigate('/recipe', {
        state: {
          recipeData: result,
          preferences,
          confirmedIngredients,
          savedRecord,
          selectedDish: finalPayload.selected_dish,
        },
      })
    } catch (err) {
      console.error('Recipe generation error:', err)
      setIsGeneratingRecipe(false)
      setGenerationError(true)
    }
  }

  // Reset entire flow to cook another recipe
  const _handleResetAll = () => {
    handleClearCurrentSlot()
    setConfirmedIngredients([])
    setRecipeRequestPayload(null)
    setError(null)
    sessionStorage.removeItem('dishgenie_confirmed_ingredients')
    sessionStorage.removeItem('dishgenie_recipe_data')
    if (uploadAreaRef.current) {
      uploadAreaRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }

  // Navigate back to preferences from recipe result
  const _handleEditPreferences = () => {
    if (preferencesRef.current) {
      preferencesRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }

  // Determine active step for stepper progress indicator
  const currentStep =
    confirmedIngredients.length === 0
      ? 1
      : isGeneratingRecipe
      ? 3
      : 2

  return (
    <div className="min-h-[85vh] py-10 md:py-16 px-4 sm:px-6 lg:px-8 max-w-5xl mx-auto space-y-10">
      
      {/* Top Header & Navigation */}
      <div className="flex items-center justify-between">
        <Link
          to="/"
          className="inline-flex items-center gap-2 text-sm font-semibold text-stone-600 hover:text-orange-600 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Back to Home</span>
        </Link>

        {confirmedIngredients.length > 0 && (
          <div className="text-xs font-semibold px-3 py-1 rounded-full bg-emerald-50 text-emerald-800 border border-emerald-200">
            {confirmedIngredients.length} ingredient{confirmedIngredients.length !== 1 ? 's' : ''} in pantry
          </div>
        )}
      </div>

      {/* Page Title */}
      <div className="text-center max-w-2xl mx-auto">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-orange-100/80 border border-orange-200 text-orange-800 text-xs font-semibold shadow-xs mb-3">
          <Sparkles className="w-3.5 h-3.5 text-orange-600" />
          <span>AI Ingredient & Recipe Pipeline</span>
        </div>
        <h1 className="text-3xl sm:text-4xl lg:text-5xl font-extrabold tracking-tight text-stone-900">
          What's in your kitchen?
        </h1>
        <p className="mt-3 text-base sm:text-lg text-stone-600">
          Upload an image and let DishGenie identify your ingredients.
        </p>
      </div>

      {/* Visual Workflow Progress Stepper */}
      <div className="bg-white rounded-2xl p-4 sm:p-5 border border-stone-200 shadow-xs max-w-2xl mx-auto">
        <div className="flex items-center justify-between text-xs sm:text-sm font-bold">
          
          {/* Step 1: Ingredients */}
          <div className="flex items-center gap-2 sm:gap-2.5">
            <span
              className={`w-7 h-7 rounded-full flex items-center justify-center font-mono text-xs transition-colors ${
                currentStep >= 1
                  ? 'bg-orange-500 text-white shadow-xs'
                  : 'bg-stone-200 text-stone-600'
              }`}
            >
              {confirmedIngredients.length > 0 ? '✓' : '1'}
            </span>
            <span className={currentStep === 1 ? 'text-orange-600 font-extrabold' : 'text-stone-700'}>
              Ingredients
            </span>
          </div>

          <span className="text-stone-300 font-bold">→</span>

          {/* Step 2: Preferences */}
          <div className="flex items-center gap-2 sm:gap-2.5">
            <span
              className={`w-7 h-7 rounded-full flex items-center justify-center font-mono text-xs transition-colors ${
                currentStep >= 2
                  ? 'bg-orange-500 text-white shadow-xs'
                  : 'bg-stone-200 text-stone-500'
              }`}
            >
              2
            </span>
            <span className={currentStep === 2 ? 'text-orange-600 font-extrabold' : 'text-stone-500'}>
              Preferences
            </span>
          </div>

          <span className="text-stone-300 font-bold">→</span>

          {/* Step 3: Recipe */}
          <div className="flex items-center gap-2 sm:gap-2.5">
            <span
              className={`w-7 h-7 rounded-full flex items-center justify-center font-mono text-xs transition-colors ${
                currentStep === 3
                  ? 'bg-emerald-600 text-white shadow-xs'
                  : 'bg-stone-200 text-stone-400'
              }`}
            >
              3
            </span>
            <span className={currentStep === 3 ? 'text-emerald-700 font-extrabold' : 'text-stone-400'}>
              <span className="hidden sm:inline">Generate </span>Recipe
            </span>
          </div>

        </div>
      </div>

      {/* Notice / Error Alert (only for non-image errors) */}
      {error && !predictionFailed && (
        <div className="p-4 rounded-2xl bg-rose-50 border border-rose-200 flex items-start gap-3 text-rose-800 text-sm shadow-xs animate-in fade-in duration-200" role="alert">
          <AlertCircle className="w-5 h-5 text-rose-600 shrink-0 mt-0.5" aria-hidden="true" />
          <div className="flex-1">
            <p className="font-semibold">Notice</p>
            <p className="mt-0.5 text-rose-700">{error}</p>
          </div>
          <button
            onClick={() => setError(null)}
            className="text-rose-500 hover:text-rose-700 font-bold px-2 py-0.5 rounded-md hover:bg-rose-100/60 cursor-pointer"
            aria-label="Close error notice"
          >
            ✕
          </button>
        </div>
      )}

      {/* SECTION 1: INGREDIENTS DETECTION & SCANNING ZONE */}
      <div ref={uploadAreaRef} className="space-y-6">
        
        {/* Upload Card */}
        <div className="bg-white rounded-3xl p-6 sm:p-8 border border-stone-200 shadow-xl shadow-stone-900/5">
          <div className="flex items-center justify-between pb-4 mb-4 border-b border-stone-100">
            <div>
              <h2 className="text-lg font-bold text-stone-900">
                1. Image & Ingredient Scanner
              </h2>
              <p className="text-xs text-stone-500">
                Capture or upload vegetable photos for AI analysis
              </p>
            </div>
            <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-orange-50 text-orange-700 border border-orange-200">
              Vision AI Active
            </span>
          </div>

          {/* Sub-State A: No Image in current upload slot */}
          {!previewUrl ? (
            <div
              role="button"
              tabIndex={0}
              onDragEnter={handleDragEnter}
              onDragLeave={handleDragLeave}
              onDragOver={handleDragOver}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  fileInputRef.current?.click()
                }
              }}
              className={`border-2 border-dashed rounded-2xl p-8 sm:p-12 text-center cursor-pointer transition-all duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-orange-500 focus-visible:ring-offset-2 ${
                dragActive
                  ? 'border-orange-500 bg-orange-50/60 scale-[1.01]'
                  : 'border-stone-300 hover:border-orange-400 hover:bg-stone-50/60'
              }`}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".jpg,.jpeg,.png,.webp"
                onChange={handleInputChange}
                className="hidden"
                aria-label="Upload an ingredient image"
              />
              <div className="w-16 h-16 mx-auto mb-4 rounded-2xl bg-orange-50 border border-orange-100 flex items-center justify-center text-orange-600 shadow-xs">
                <UploadCloud className="w-8 h-8" aria-hidden="true" />
              </div>
              <h3 className="text-lg font-bold text-stone-900">
                Upload an ingredient image
              </h3>
              <p className="text-sm text-stone-500 mt-1">
                Drag & drop your vegetable image here, or <span className="text-orange-600 font-semibold underline underline-offset-2">browse files</span> from your device
              </p>
              <div className="mt-4 flex items-center justify-center gap-2 text-xs text-stone-400">
                <span className="px-2 py-1 rounded-md bg-stone-100 font-mono">JPG</span>
                <span className="px-2 py-1 rounded-md bg-stone-100 font-mono">JPEG</span>
                <span className="px-2 py-1 rounded-md bg-stone-100 font-mono">PNG</span>
                <span className="text-stone-300">•</span>
                <span>Max 10MB</span>
              </div>
            </div>
          ) : (
            /* Sub-State B: Image Selected (Preview + Trigger Detect) */
            <div className="space-y-6">
              <div className="flex flex-col sm:flex-row items-center gap-6 p-4 rounded-2xl bg-stone-50 border border-stone-200/80">
                <div className="relative w-40 h-40 rounded-xl overflow-hidden bg-stone-200 border border-stone-300 shrink-0 shadow-inner">
                  <img
                    src={previewUrl}
                    alt="Selected ingredient"
                    className="w-full h-full object-cover"
                  />
                </div>

                <div className="flex-1 w-full flex flex-col justify-between h-full py-1">
                  <div>
                    <div className="flex items-center gap-2 text-xs text-stone-500 mb-1">
                      <FileImage className="w-4 h-4 text-stone-400" aria-hidden="true" />
                      <span>Ready to analyze</span>
                    </div>
                    <h4 className="font-bold text-stone-900 text-base break-all">
                      {selectedImage?.name}
                    </h4>
                    <p className="text-xs text-stone-500 mt-1">
                      {(selectedImage?.size / (1024 * 1024)).toFixed(2)} MB • {selectedImage?.type}
                    </p>
                  </div>

                  <div className="pt-4 flex flex-wrap items-center gap-3">
                    <button
                      type="button"
                      onClick={handleClearCurrentSlot}
                      disabled={isPredicting}
                      className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold text-rose-600 hover:text-rose-700 bg-white hover:bg-rose-50 border border-rose-200 transition-colors disabled:opacity-50 cursor-pointer"
                    >
                      <Trash2 className="w-3.5 h-3.5" aria-hidden="true" />
                      <span>Remove</span>
                    </button>

                    <button
                      type="button"
                      onClick={() => fileInputRef.current?.click()}
                      disabled={isPredicting}
                      className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold text-stone-700 hover:text-stone-900 bg-white hover:bg-stone-100 border border-stone-200 transition-colors disabled:opacity-50 cursor-pointer"
                    >
                      <RefreshCw className="w-3.5 h-3.5" aria-hidden="true" />
                      <span>Choose Different Photo</span>
                    </button>
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept=".jpg,.jpeg,.png,.webp"
                      onChange={handleInputChange}
                      className="hidden"
                      aria-label="Choose different ingredient photo"
                    />
                  </div>
                </div>
              </div>

              {/* Action Trigger Button if not yet predicted */}
              {!prediction && !predictionFailed && (
                <div className="pt-2 flex justify-center">
                  <button
                    type="button"
                    onClick={handleDetect}
                    disabled={isPredicting}
                    className="w-full sm:w-auto min-w-[240px] inline-flex items-center justify-center gap-2.5 px-8 py-4 rounded-full text-base font-bold text-white bg-gradient-to-r from-orange-500 to-amber-600 hover:from-orange-600 hover:to-amber-700 shadow-lg shadow-orange-500/25 transition-all duration-200 disabled:opacity-60 disabled:cursor-not-allowed cursor-pointer"
                  >
                    {isPredicting ? (
                      <>
                        <Loader2 className="w-5 h-5 animate-spin" aria-hidden="true" />
                        <span>Analyzing your ingredient...</span>
                      </>
                    ) : (
                      <>
                        <Sparkles className="w-5 h-5" aria-hidden="true" />
                        <span>Detect Ingredients</span>
                      </>
                    )}
                  </button>
                </div>
              )}

              {/* Section 4: Image Prediction Error State */}
              {predictionFailed && (
                <div className="p-6 rounded-2xl bg-rose-50 border border-rose-200 text-center space-y-4 animate-in fade-in duration-200" role="alert">
                  <div className="w-12 h-12 mx-auto rounded-2xl bg-rose-100 border border-rose-200 flex items-center justify-center text-rose-600">
                    <AlertCircle className="w-6 h-6" aria-hidden="true" />
                  </div>
                  <div className="space-y-1">
                    <h3 className="text-base font-bold text-stone-900">
                      We couldn't analyze this image.
                    </h3>
                    <p className="text-xs sm:text-sm text-stone-600 max-w-md mx-auto leading-relaxed">
                      {error || "The image could not be processed. Please try again or upload a clearer photo."}
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center justify-center gap-3 pt-1">
                    <button
                      type="button"
                      onClick={handleDetect}
                      disabled={isPredicting}
                      className="inline-flex items-center gap-1.5 px-5 py-2.5 rounded-full text-xs font-bold text-white bg-gradient-to-r from-orange-500 to-amber-600 hover:from-orange-600 hover:to-amber-700 shadow-sm transition-all cursor-pointer"
                    >
                      <RotateCcw className="w-3.5 h-3.5" aria-hidden="true" />
                      <span>Try Again</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        handleClearCurrentSlot()
                        setTimeout(() => fileInputRef.current?.click(), 100)
                      }}
                      className="inline-flex items-center gap-1.5 px-5 py-2.5 rounded-full text-xs font-semibold text-stone-700 bg-white hover:bg-stone-100 border border-stone-300 transition-colors cursor-pointer"
                    >
                      <RefreshCw className="w-3.5 h-3.5" aria-hidden="true" />
                      <span>Choose Another Image</span>
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Loading Spinner Card (Section 3) */}
        {isPredicting && (
          <LoadingState
            message="Analyzing your ingredient..."
            subMessage="Please wait while DishGenie identifies your vegetable."
            variant="card"
          />
        )}

        {/* Prediction Results, Annotated Image & Inventory Confirmation Area */}
        {prediction && !isPredicting && (
          <div className="space-y-8 animate-in fade-in duration-300">
            
            {/* Visual Multi-Item Detection & Bounding Boxes Preview */}
            <div className="bg-white rounded-3xl p-6 sm:p-8 border border-stone-200 shadow-xl shadow-stone-900/5">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-5 border-b border-stone-100 gap-3">
                <div className="flex items-center gap-2.5">
                  <span className="inline-flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-orange-700 bg-orange-50 px-3 py-1.5 rounded-full border border-orange-200">
                    <Boxes className="w-3.5 h-3.5 text-orange-600" />
                    Detected Ingredients
                  </span>
                  <span className="text-xs font-bold text-emerald-700 bg-emerald-50 px-2.5 py-1 rounded-full border border-emerald-200">
                    {totalDetectedItems} item{totalDetectedItems === 1 ? '' : 's'}
                  </span>
                </div>

                {annotatedImage && detections.length > 0 && (
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => setShowAnnotated(!showAnnotated)}
                      className="inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-xl border border-stone-200 bg-stone-50 hover:bg-stone-100 text-stone-700 transition cursor-pointer"
                    >
                      {showAnnotated ? (
                        <>
                          <EyeOff className="w-3.5 h-3.5 text-stone-500" />
                          <span>Show Original Photo</span>
                        </>
                      ) : (
                        <>
                          <Eye className="w-3.5 h-3.5 text-orange-600" />
                          <span>Show Bounding Boxes</span>
                        </>
                      )}
                    </button>
                  </div>
                )}
              </div>

              {/* Grid: Annotated Visualizer on Left, Model Confidence on Right */}
              <div className="mt-6 grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
                {/* Visualizer Frame */}
                <div className="lg:col-span-6 bg-stone-950 rounded-2xl overflow-hidden border border-stone-800 shadow-inner relative flex items-center justify-center min-h-[260px] max-h-[380px]">
                  {annotatedImage && detections.length > 0 && showAnnotated ? (
                    <img
                      src={annotatedImage}
                      alt="Annotated detection with bounding boxes"
                      className="w-full h-full object-contain max-h-[380px]"
                    />
                  ) : (
                    <img
                      src={previewUrl}
                      alt="Uploaded produce"
                      className="w-full h-full object-contain max-h-[380px]"
                    />
                  )}
                </div>

                {/* What was found */}
                <div className="lg:col-span-6 flex flex-col gap-4">
                  <div>
                    <h2 className="text-lg font-extrabold text-stone-900">
                      Found {inventory.length} ingredient{inventory.length === 1 ? '' : 's'} in your photo
                    </h2>
                    <p className="text-sm text-stone-500 mt-0.5">
                      Check the list. Fix a count, remove a wrong item, or add one we missed.
                    </p>
                  </div>
                  <ul className="flex flex-wrap gap-2.5">
                    {inventory.map((item) => (
                      <li
                        key={item.ingredient}
                        className="inline-flex items-center gap-2 pl-3 pr-3.5 py-2 rounded-2xl bg-stone-50 border border-stone-200 text-sm font-bold text-stone-800"
                      >
                        <span className="text-xl" aria-hidden="true">{INGREDIENT_EMOJIS[item.ingredient] || '🥗'}</span>
                        <span>{formatIngredientName(item.ingredient)}</span>
                        <span className="font-mono text-xs px-1.5 py-0.5 rounded-md bg-orange-100 text-orange-700">×{item.count}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>

              {/* Editable Multi-Item Produce Inventory Table */}
              <div className="mt-8 pt-6 border-t border-stone-100">
                <InventoryTable
                  inventory={inventory}
                  onUpdateInventory={handleUpdateInventory}
                  onRemoveItem={handleRemoveInventoryItem}
                  onAddItem={handleAddInventoryItem}
                />
              </div>

              {/* Confirmation Action Bar */}
              <div className="mt-8 pt-6 border-t border-stone-100 bg-stone-50/80 p-5 rounded-2xl">
                <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
                  <div>
                    <h3 className="text-sm font-bold text-stone-900">
                      Confirm Inventory & Recipe Setup
                    </h3>
                    <p className="text-xs text-stone-500">
                      Counts, freshness grading, and expiry days will be used by the recipe AI.
                    </p>
                  </div>

                  {!isChanging ? (
                    <div className="flex flex-wrap items-center gap-3">
                      <button
                        type="button"
                        onClick={handleConfirmAllInventory}
                        className="inline-flex items-center gap-2 px-6 py-2.5 rounded-full text-xs font-bold text-white bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-700 hover:to-teal-700 shadow-md shadow-emerald-900/10 transition-all hover:-translate-y-0.5 cursor-pointer"
                      >
                        <Check className="w-4 h-4" />
                        <span>✓ Confirm & Continue</span>
                      </button>

                      <button
                        type="button"
                        onClick={handleClearCurrentSlot}
                        className="inline-flex items-center gap-1.5 px-3.5 py-2.5 rounded-full text-xs font-semibold text-stone-500 hover:text-stone-700 bg-transparent hover:bg-stone-200/50 transition cursor-pointer"
                        title="Upload another photo"
                      >
                        <RotateCcw className="w-3.5 h-3.5" />
                        <span>Reset</span>
                      </button>
                    </div>
                  ) : (
                    <div className="w-full">
                      <IngredientSelector
                        currentSelection={prediction.name}
                        onSelect={(selectedClass) => {
                          setIsChanging(false)
                          handleConfirmIngredient(selectedClass)
                        }}
                        onCancel={() => setIsChanging(false)}
                      />
                    </div>
                  )}
                </div>
              </div>

            </div>
          </div>
        )}

        {/* Confirmed Ingredients List View (MULTIPLE INGREDIENTS) */}
        <IngredientList
          ingredients={confirmedIngredients}
          onRemove={handleRemoveConfirmed}
          onAddAnother={handleAddAnother}
          onQuickAdd={() => setShowManualPicker(true)}
        />

        {/* Quick Add from 247 Classes Modal */}
        {showManualPicker && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-stone-900/60 backdrop-blur-xs animate-in fade-in duration-200">
            <div className="max-w-xl w-full">
              <IngredientSelector
                onSelect={(selectedClass) => {
                  setShowManualPicker(false)
                  handleConfirmIngredient(selectedClass)
                }}
                onCancel={() => setShowManualPicker(false)}
              />
            </div>
          </div>
        )}

      </div>

      {/* SECTION 2: RECIPE PREFERENCES (Unlocked when at least 1 ingredient is confirmed) */}
      {confirmedIngredients.length > 0 && (
        <div ref={preferencesRef} className="space-y-8 pt-4">
          <RecipePreferences
            preferences={preferences}
            onChange={(newPrefs) => {
              setPreferences(newPrefs)
              setPreferenceErrors({})
            }}
            onSubmit={handleGenerateRecipe}
            ingredientsCount={confirmedIngredients.length}
            isGenerating={isGeneratingRecipe}
            errors={preferenceErrors}
          />
        </div>
      )}

      {/* SECTION 3: DEDICATED FULL-PAGE LOADING STATE (Section 8) */}
      {isGeneratingRecipe && (
        <div className="fixed inset-0 z-50 bg-[#faf8f5]/95 backdrop-blur-md flex flex-col items-center justify-center p-6 text-center animate-in fade-in duration-300" role="status" aria-live="polite">
          <div className="max-w-md w-full space-y-7">
            {/* Animated cooking icon container */}
            <div className="relative w-28 h-28 mx-auto flex items-center justify-center">
              <div className="absolute inset-0 rounded-full bg-gradient-to-tr from-orange-400 to-amber-300 opacity-25 blur-xl animate-pulse"></div>
              <div className="w-24 h-24 rounded-3xl bg-white border border-orange-200 shadow-xl flex items-center justify-center text-4xl animate-simmer">
                🍳
              </div>
              <div className="absolute -top-2 -right-2 w-8 h-8 rounded-full bg-orange-500 text-white flex items-center justify-center shadow-md animate-bounce">
                <Sparkles className="w-4 h-4" aria-hidden="true" />
              </div>
            </div>

            <div className="space-y-2">
              <h2 className="text-2xl sm:text-3xl font-extrabold text-stone-900 tracking-tight">
                {selectedDishName ? `Synthesizing ${selectedDishName}...` : 'Creating your recipe...'}
              </h2>
              <p className="text-xs sm:text-sm text-stone-600 max-w-sm mx-auto leading-relaxed">
                {selectedDishName
                  ? 'Our AI chef is tailoring the steps and ingredients to your selection.'
                  : 'Please wait while DishGenie prepares your recipe.'}
              </p>
            </div>

            {/* 3 Step-by-Step UI Feedback Stages */}
            <div className="bg-white rounded-2xl p-4 sm:p-5 border border-stone-200 shadow-sm space-y-3 text-left">
              {loadingStages.map((stageName, idx) => {
                const isActive = currentLoadingStage === idx
                const isPassed = currentLoadingStage > idx
                return (
                  <div
                    key={stageName}
                    className={`flex items-center gap-3 p-2.5 rounded-xl transition-all duration-300 ${
                      isActive
                        ? 'bg-orange-50 border border-orange-200 text-orange-950 font-bold shadow-2xs'
                        : isPassed
                        ? 'text-stone-700 font-medium'
                        : 'text-stone-400'
                    }`}
                  >
                    <div className="shrink-0">
                      {isActive ? (
                        <Loader2 className="w-4 h-4 text-orange-600 animate-spin" aria-hidden="true" />
                      ) : isPassed ? (
                        <Check className="w-4 h-4 text-emerald-600" aria-hidden="true" />
                      ) : (
                        <span className="w-4 h-4 rounded-full border border-stone-300 inline-block"></span>
                      )}
                    </div>
                    <span className="text-xs sm:text-sm">{stageName}</span>
                  </div>
                )
              })}
            </div>

            <p className="text-[11px] text-stone-400">
              Running locally on-device via local AI models and a recipe database without cloud AI APIs.
            </p>
          </div>
        </div>
      )}

      {/* SECTION 4: FRIENDLY ERROR STATE (Section 9) */}
      {generationError && (
        <div className="fixed inset-0 z-50 bg-stone-900/50 backdrop-blur-sm flex flex-col items-center justify-center p-6 text-center animate-in fade-in duration-200" role="alert">
          <div className="max-w-md w-full bg-white rounded-3xl p-8 border border-stone-200 shadow-2xl text-center space-y-6">
            <div className="w-16 h-16 mx-auto rounded-2xl bg-rose-50 border border-rose-200 flex items-center justify-center text-rose-500">
              <AlertCircle className="w-8 h-8" aria-hidden="true" />
            </div>

            <div className="space-y-2">
              <h2 className="text-xl sm:text-2xl font-extrabold text-stone-900">
                Unable to generate your recipe.
              </h2>
              <p className="text-xs sm:text-sm text-stone-600 leading-relaxed">
                The local AI service encountered an issue while generating your recipe. Your ingredients and preferences have been preserved.
              </p>
            </div>

            <div className="pt-2 flex flex-col sm:flex-row items-center justify-center gap-3">
              <button
                type="button"
                onClick={() => {
                  setGenerationError(false)
                  proceedToDishOptions()
                }}
                className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-6 py-3 rounded-full text-xs font-bold text-white bg-gradient-to-r from-orange-500 to-amber-600 hover:from-orange-600 hover:to-amber-700 shadow-md shadow-orange-500/20 cursor-pointer"
              >
                <RotateCcw className="w-4 h-4" aria-hidden="true" />
                <span>Try Again</span>
              </button>

              <button
                type="button"
                onClick={() => {
                  setGenerationError(false)
                  if (uploadAreaRef.current) {
                    uploadAreaRef.current.scrollIntoView({ behavior: 'smooth' })
                  }
                }}
                className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-6 py-3 rounded-full text-xs font-semibold text-stone-700 bg-stone-100 hover:bg-stone-200 transition-colors cursor-pointer"
              >
                <ArrowLeft className="w-4 h-4" aria-hidden="true" />
                <span>Back to Ingredients</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* SECTION 5: RECIPE REQUEST DATA MODAL (Structured Output Object) */}
      {showPayloadModal && (
        <RecipeRequestModal
          requestPayload={recipeRequestPayload}
          isLoading={isLoadingCandidates}
          onClose={() => setShowPayloadModal(false)}
          onAccept={proceedToDishOptions}
          onEdit={() => {
            setShowPayloadModal(false)
            if (preferencesRef.current) {
              preferencesRef.current.scrollIntoView({ behavior: 'smooth' })
            }
          }}
        />
      )}

      {/* INTERACTIVE RECIPE SELECTION MODAL ("Choose Your Dish Option") */}
      <DishOptionsModal
        isOpen={showOptionsModal}
        onClose={() => setShowOptionsModal(false)}
        options={dishOptions}
        onSelectOption={handleSelectDishOption}
        onAutoGenerate={handleAutoGenerateWithoutDish}
        isGenerating={isGeneratingRecipe}
        selectedDishName={selectedDishName}
      />

      {/* Subtle Toast Feedback (Section 16) */}
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
