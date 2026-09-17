import os, urllib.request
URL='https://huggingface.co/SpeechAntiSpoofingBenchmarks/AASIST/resolve/main/aasist.onnx?download=true'
os.makedirs('model', exist_ok=True)
out='model/aasist.onnx'
if not os.path.exists(out) or os.path.getsize(out) < 500_000:
    tmp=out+'.part'
    print('Downloading official AASIST ONNX checkpoint…')
    urllib.request.urlretrieve(URL,tmp)
    os.replace(tmp,out)
print('AASIST model ready:', os.path.getsize(out),'bytes')
