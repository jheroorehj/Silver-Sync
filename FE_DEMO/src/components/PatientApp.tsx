import React, { useState } from 'react';
import QRCode from 'react-qr-code';
import { MapPin, Clock, CheckCircle, Navigation, ArrowLeft, Pill } from 'lucide-react';

export default function PatientApp() {
  const [view, setView] = useState<'home' | 'pharmacy'>('home');

  return (
    <div className="max-w-md mx-auto bg-slate-50 min-h-screen flex flex-col relative font-sans selection:bg-sky-200 overflow-hidden">
      {view === 'home' && (
        <div className="flex-1 flex flex-col items-center justify-between py-12 px-8 animate-in fade-in duration-700">
          <div className="text-center space-y-2">
            <p className="text-3xl font-bold text-slate-800 leading-tight">
              김덕배 님,
            </p>
            <p className="text-4xl font-black text-sky-700 leading-tight">
              약국에 보여주세요
            </p>
          </div>

          <div className="bg-white p-8 rounded-3xl shadow-xl shadow-slate-200/50 border border-slate-100">
            <QRCode 
              value="https://silver-sync.app/prescription/12345" 
              size={260}
              level="H"
              fgColor="#1e293b"
            />
          </div>

          <button 
            onClick={() => setView('pharmacy')}
            className="w-full h-20 bg-sky-100 text-sky-900 rounded-2xl font-black text-2xl shadow-md active:scale-[0.98] transition-all flex items-center justify-center border-2 border-sky-200"
          >
            <MapPin className="w-8 h-8 mr-3 text-sky-600" strokeWidth={3} />
            가까운 약국 찾기
          </button>
        </div>
      )}

      {view === 'pharmacy' && (
        <div className="flex-1 flex flex-col animate-in slide-in-from-right-8 duration-700 pb-12">
          {/* Map Placeholder */}
          <div className="h-72 bg-slate-200 relative overflow-hidden shadow-inner">
            <button 
              onClick={() => setView('home')}
              className="absolute top-4 left-4 z-50 w-12 h-12 bg-white rounded-xl shadow-lg flex items-center justify-center active:scale-90 transition-transform border border-slate-200"
            >
              <ArrowLeft className="w-6 h-6 text-slate-700" strokeWidth={3} />
            </button>
            <img 
              src="https://picsum.photos/seed/map/800/600" 
              alt="지도" 
              className="w-full h-full object-cover opacity-60 grayscale-[20%]"
              referrerPolicy="no-referrer"
            />
            {/* Current Location Marker - Smaller */}
            <div className="absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2">
              <div className="w-8 h-8 bg-sky-500 rounded-full border-4 border-white shadow-lg"></div>
            </div>
            {/* Pharmacy Marker - Smaller and less intrusive */}
            <div className="absolute top-1/3 left-2/3 transform -translate-x-1/2 -translate-y-1/2">
              <div className="bg-white/90 backdrop-blur-sm px-4 py-2 rounded-xl shadow-md font-bold text-lg text-slate-800 flex items-center border border-sky-200">
                <div className="w-3 h-3 rounded-full bg-emerald-500 mr-2"></div>
                행복약국
              </div>
            </div>
          </div>

          {/* Pharmacy List */}
          <div className="flex-1 bg-slate-50 px-6 pt-8 space-y-4 overflow-y-auto no-scrollbar">
            <h2 className="text-2xl font-black text-slate-800 mb-2 tracking-tight text-center">가까운 약국 목록</h2>
            
            {[
              { name: '행복 온누리 약국', dist: '350m', stock: true },
              { name: '건강제일 약국', dist: '800m', stock: true },
              { name: '사랑 약국', dist: '1.2km', stock: false },
            ].map((pharm, idx) => (
              <div key={idx} className={`bg-white rounded-2xl p-6 shadow-sm border ${pharm.stock ? 'border-slate-200' : 'border-slate-100 opacity-60'}`}>
                <div className="flex justify-between items-center mb-3">
                  <h3 className="text-xl font-bold text-slate-800 tracking-tight">{pharm.name}</h3>
                  {pharm.stock ? (
                    <span className="text-emerald-600 text-base font-bold">약 있음</span>
                  ) : (
                    <span className="text-slate-400 text-base font-bold">재고 없음</span>
                  )}
                </div>
                
                <div className="flex items-center text-lg font-medium text-slate-500 mb-4">
                  <Clock className="w-5 h-5 mr-2 text-sky-400" /> {pharm.dist}
                </div>
                
                {pharm.stock && (
                  <button className="w-full h-16 bg-sky-50 text-sky-700 rounded-xl flex items-center justify-center font-bold text-xl active:scale-[0.98] transition-all border border-sky-100">
                    <Navigation className="w-6 h-6 mr-2" strokeWidth={3} /> 길찾기
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
