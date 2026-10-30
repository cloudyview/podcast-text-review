import Foundation
let data = FileHandle.standardInput.readDataToEndOfFile()
let s = String(data:data,encoding:.utf8)!
let result = s.applyingTransform(StringTransform("Traditional-Simplified"), reverse:false) ?? s
FileHandle.standardOutput.write(result.data(using:.utf8)!)
