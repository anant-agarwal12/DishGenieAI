import { Link } from 'react-router-dom'
import { ArrowRight, UtensilsCrossed } from 'lucide-react'

export default function CTA() {
  return (
    <section className="py-20 md:py-28 bg-[#faf8f5]">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
        
        {/* Card Box */}
        <div className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-stone-900 via-stone-800 to-amber-950 text-white p-10 sm:p-14 lg:p-16 shadow-2xl text-center">
          
          {/* Subtle Ambient Glow */}
          <div className="absolute -top-24 -right-24 w-72 h-72 bg-orange-500/20 rounded-full blur-3xl pointer-events-none"></div>
          <div className="absolute -bottom-24 -left-24 w-72 h-72 bg-amber-500/20 rounded-full blur-3xl pointer-events-none"></div>

          {/* Icon Badge */}
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-white/10 backdrop-blur-xs border border-white/15 text-orange-400 mb-6 shadow-inner">
            <UtensilsCrossed className="w-7 h-7" />
          </div>

          {/* Heading */}
          <h2 className="text-3xl sm:text-4xl lg:text-5xl font-extrabold tracking-tight text-white max-w-2xl mx-auto leading-tight">
            Ready to discover what's in your kitchen?
          </h2>

          {/* Supporting Text */}
          <p className="mt-4 text-base sm:text-lg text-stone-300 max-w-xl mx-auto leading-relaxed">
            Let DishGenie turn your ingredients into your next favorite meal.
          </p>

          {/* Button */}
          <div className="mt-8 flex flex-col sm:flex-row items-center justify-center gap-4">
            <Link
              to="/detect"
              className="w-full sm:w-auto inline-flex items-center justify-center gap-2.5 px-8 py-4 rounded-full text-base font-bold text-stone-900 bg-gradient-to-r from-amber-400 to-orange-400 hover:from-amber-300 hover:to-orange-300 shadow-lg shadow-orange-500/30 hover:shadow-orange-500/40 transition-all duration-200 hover:-translate-y-0.5 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-400 focus-visible:ring-offset-2 focus-visible:ring-offset-stone-900"
            >
              <span>Start Cooking</span>
              <ArrowRight className="w-5 h-5 text-stone-900" />
            </Link>
          </div>

          <p className="mt-6 text-xs text-stone-400">
            Powered by Local Vision AI & Fast On-Device Inference
          </p>

        </div>

      </div>
    </section>
  )
}
