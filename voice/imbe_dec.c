#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <math.h>
#include "mbelib.h"

static void le16(FILE*f,uint16_t v){fputc(v&0xff,f);fputc((v>>8)&0xff,f);}
static void le32(FILE*f,uint32_t v){for(int i=0;i<4;i++){fputc(v&0xff,f);v>>=8;}}

int main(int argc,char**argv){
  if(argc<4){fprintf(stderr,"usage: %s in.ambe out.wav msb|lsb\n",argv[0]);return 2;}
  int msb=!strcmp(argv[3],"msb");
  FILE*fi=fopen(argv[1],"rb"); if(!fi){perror("in");return 1;}
  fseek(fi,0,SEEK_END); long n=ftell(fi); fseek(fi,0,SEEK_SET);
  unsigned char*buf=malloc(n); if(fread(buf,1,n,fi)!=(size_t)n){return 1;} fclose(fi);
  long frames=n/11;
  mbe_parms cur,prev,penh; mbe_initMbeParms(&cur,&prev,&penh);
  short*audio=malloc(frames*160*sizeof(short)); long outn=0;
  int errs=0,errs2=0; char es[64]={0}; double sumsq=0; long clip=0; long toterr=0;
  for(long f=0;f<frames;f++){
    unsigned char*fr=buf+f*11; char d[88];
    for(int i=0;i<88;i++){int by=i/8,bi=i%8; d[i]=(char)(msb?((fr[by]>>(7-bi))&1):((fr[by]>>bi)&1));}
    short a[160];
    mbe_processImbe4400Data(a,&errs,&errs2,es,d,&cur,&prev,&penh,3);
    toterr+=errs;
    for(int i=0;i<160;i++){audio[outn+i]=a[i]; sumsq+=(double)a[i]*a[i]; if(a[i]>=32760||a[i]<=-32760)clip++;}
    outn+=160;
  }
  FILE*fo=fopen(argv[2],"wb"); uint32_t dl=outn*2;
  fwrite("RIFF",1,4,fo); le32(fo,36+dl); fwrite("WAVE",1,4,fo);
  fwrite("fmt ",1,4,fo); le32(fo,16); le16(fo,1); le16(fo,1);
  le32(fo,8000); le32(fo,16000); le16(fo,2); le16(fo,16);
  fwrite("data",1,4,fo); le32(fo,dl); fwrite(audio,2,outn,fo); fclose(fo);
  fprintf(stderr,"frames=%ld samples=%ld rms=%.1f clip=%ld eccErrsTotal=%ld\n",
          frames,outn,outn?sqrt(sumsq/outn):0.0,clip,toterr);
  return 0;
}
