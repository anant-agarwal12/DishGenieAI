import { Clock, Users, ChefHat, Check, Sparkles } from 'lucide-react'

export default function RecipePreview() {
  const ingredients = [
    { name: 'Tomato', detail: '4 ripe vine tomatoes, diced' },
    { name: 'Pasta', detail: '200g penne or fettuccine' },
    { name: 'Garlic', detail: '3 cloves, finely minced' },
    { name: 'Onion', detail: '1 small yellow onion, chopped' },
    { name: 'Olive oil', detail: '2 tablespoons extra virgin' },
  ]

  const instructions = [
    'Bring a large pot of salted water to a rolling boil. Cook pasta until al dente, reserving 1/2 cup pasta water before draining.',
    'Heat extra virgin olive oil in a skillet over medium heat. Sauté diced onions for 3-4 minutes until translucent, then add minced garlic and sauté for 1 minute until fragrant.',
    'Add diced tomatoes and simmer gently on low heat for 10-12 minutes until sauce thickens. Stir in 2 tablespoons of cream or reserved pasta water for a silky finish.',
    'Toss the drained pasta into the skillet, coating thoroughly. Garnish with torn fresh basil leaves, cracked black pepper, and serve immediately.',
  ]

  return (
    <section id="recipe-preview" className="py-20 md:py-28 bg-white border-b border-stone-200/80">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        
        {/* Section Header */}
        <div className="text-center max-w-3xl mx-auto mb-16">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-orange-50 border border-orange-200 text-orange-700 text-xs font-semibold uppercase tracking-wider mb-3">
            <Sparkles className="w-3.5 h-3.5 text-orange-600" />
            Output Preview
          </div>
          <h2 className="text-3xl sm:text-4xl font-extrabold tracking-tight text-stone-900">
            What You'll Create With DishGenie
          </h2>
          <p className="mt-4 text-base sm:text-lg text-stone-600">
            Here is a sample recipe card previewing the structured cooking output our Generative AI will produce.
          </p>
        </div>

        {/* Recipe Card Container */}
        <div className="max-w-4xl mx-auto bg-[#faf8f5] rounded-3xl border border-stone-200/90 shadow-xl shadow-stone-900/5 overflow-hidden">
          
          {/* Card Top Notice Bar */}
          <div className="bg-stone-900 text-stone-200 px-6 py-3 flex flex-wrap items-center justify-between gap-3 text-xs">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-amber-400"></span>
              <span className="font-semibold text-white tracking-wide uppercase text-[11px] bg-stone-800 px-2 py-0.5 rounded-md">
                Example Recipe
              </span>
              <span className="text-stone-400 hidden sm:inline">• Sample Production Output</span>
            </div>
            <div className="flex items-center gap-1.5 text-amber-300">
              <ChefHat className="w-4 h-4" />
              <span>Full Structured Synthesis Format</span>
            </div>
          </div>

          <div className="p-6 sm:p-10">
            {/* Title & Metadata Header */}
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 pb-8 border-b border-stone-200/80">
              <div>
                <span className="text-xs font-bold text-orange-600 uppercase tracking-widest">
                  Italian • Comfort Dinner
                </span>
                <h3 className="text-2xl sm:text-3xl font-extrabold text-stone-900 mt-1">
                  Creamy Tomato Pasta
                </h3>
                <p className="text-sm text-stone-600 mt-2 max-w-xl">
                  A comforting pasta dish featuring blistered fresh tomatoes, fragrant garlic, and a velvety olive oil emulsion.
                </p>
              </div>

              {/* Badges Pill Box */}
              <div className="flex flex-wrap md:flex-nowrap items-center gap-3">
                <div className="flex items-center gap-2 px-3.5 py-2 rounded-2xl bg-white border border-stone-200 shadow-xs text-xs font-semibold text-stone-700">
                  <Clock className="w-4 h-4 text-orange-500" />
                  <span>⏱ 30 min</span>
                </div>
                <div className="flex items-center gap-2 px-3.5 py-2 rounded-2xl bg-white border border-stone-200 shadow-xs text-xs font-semibold text-stone-700">
                  <ChefHat className="w-4 h-4 text-amber-500" />
                  <span>Difficulty: Easy</span>
                </div>
                <div className="flex items-center gap-2 px-3.5 py-2 rounded-2xl bg-white border border-stone-200 shadow-xs text-xs font-semibold text-stone-700">
                  <Users className="w-4 h-4 text-emerald-500" />
                  <span>Servings: 2</span>
                </div>
              </div>
            </div>

            {/* Recipe Content: Ingredients & Instructions Grid */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 pt-8">
              
              {/* Ingredients Column */}
              <div className="lg:col-span-5 space-y-4">
                <div className="flex items-center justify-between">
                  <h4 className="text-base font-bold text-stone-900 uppercase tracking-wider text-xs">
                    Ingredients ({ingredients.length})
                  </h4>
                  <span className="text-[11px] text-emerald-600 font-semibold bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200">
                    All Pantry Matched
                  </span>
                </div>

                <ul className="space-y-2.5">
                  {ingredients.map((item) => (
                    <li
                      key={item.name}
                      className="flex items-start gap-3 p-3 rounded-xl bg-white border border-stone-200/70 text-sm shadow-xs"
                    >
                      <div className="w-5 h-5 rounded-full bg-orange-100 text-orange-600 flex items-center justify-center shrink-0 mt-0.5">
                        <Check className="w-3.5 h-3.5" />
                      </div>
                      <div>
                        <span className="font-semibold text-stone-900">{item.name}</span>
                        <p className="text-xs text-stone-500">{item.detail}</p>
                      </div>
                    </li>
                  ))}
                </ul>

                {/* Planned Substitutions Callout */}
                <div className="p-3.5 rounded-xl bg-amber-50/80 border border-amber-200/80 text-xs text-amber-900 space-y-1">
                  <p className="font-bold flex items-center gap-1.5 text-amber-800">
                    <Sparkles className="w-3.5 h-3.5 text-amber-600" />
                    Planned Substitution Feature
                  </p>
                  <p className="text-amber-700">
                    No cream? GenAI will suggest pasta cooking water with a drizzle of olive oil or Greek yogurt.
                  </p>
                </div>
              </div>

              {/* Instructions Column */}
              <div className="lg:col-span-7 space-y-4">
                <h4 className="text-base font-bold text-stone-900 uppercase tracking-wider text-xs">
                  Cooking Instructions
                </h4>

                <div className="space-y-3.5">
                  {instructions.map((step, index) => (
                    <div
                      key={index}
                      className="flex items-start gap-3.5 p-4 rounded-xl bg-white border border-stone-200/70 shadow-xs"
                    >
                      <span className="w-6 h-6 rounded-lg bg-stone-900 text-white font-mono text-xs font-bold flex items-center justify-center shrink-0 mt-0.5">
                        {index + 1}
                      </span>
                      <p className="text-xs sm:text-sm text-stone-700 leading-relaxed">
                        {step}
                      </p>
                    </div>
                  ))}
                </div>
              </div>

            </div>

            {/* Bottom Clarification */}
            <div className="mt-8 pt-4 border-t border-stone-200/70 flex items-center justify-between text-xs text-stone-500">
              <div className="flex items-center gap-1.5">
                <Sparkles className="w-3.5 h-3.5 text-orange-500" />
                <span>Example recipe output synthesized by DishGenie's two-stage AI engine</span>
              </div>
              <span className="font-medium text-stone-600 hidden sm:inline">Local AI & Recipe Database</span>
            </div>

          </div>
        </div>

      </div>
    </section>
  )
}
