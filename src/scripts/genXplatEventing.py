﻿#
## Licensed to the .NET Foundation under one or more agreements.
## The .NET Foundation licenses this file to you under the MIT license.
## See the LICENSE file in the project root for more information.
#
#
#USAGE:
#Add Events: modify <root>src/vm/ClrEtwAll.man
#Look at the Code in  <root>/src/scripts/genXplatLttng.py for using subroutines in this file
#

# Python 2 compatibility
from __future__ import print_function

import os
import xml.dom.minidom as DOM

stdprolog="""
// Licensed to the .NET Foundation under one or more agreements.
// The .NET Foundation licenses this file to you under the MIT license.
// See the LICENSE file in the project root for more information.

/******************************************************************

DO NOT MODIFY. AUTOGENERATED FILE.
This file is generated using the logic from <root>/src/scripts/genXplatEventing.py

******************************************************************/
"""

stdprolog_cmake="""
#
#
#******************************************************************

#DO NOT MODIFY. AUTOGENERATED FILE.
#This file is generated using the logic from <root>/src/scripts/genXplatEventing.py

#******************************************************************
"""

lindent = "    ";
palDataTypeMapping ={
        #constructed types
        "win:null"          :" ",
        "win:Int64"         :"const __int64",
        "win:ULong"         :"const ULONG",
        "win:count"         :"*",
        "win:Struct"        :"const void",
        #actual spec
        "win:GUID"          :"const GUID",
        "win:AnsiString"    :"LPCSTR",
        "win:UnicodeString" :"PCWSTR",
        "win:Double"        :"const double",
        "win:Int32"         :"const signed int",
        "win:Boolean"       :"const BOOL",
        "win:UInt64"        :"const unsigned __int64",
        "win:UInt32"        :"const unsigned int",
        "win:UInt16"        :"const unsigned short",
        "win:UInt8"         :"const unsigned char",
        "win:Pointer"       :"const void*",
        "win:Binary"        :"const BYTE"
        }
# A Template represents an ETW template can contain 1 or more AbstractTemplates
# The AbstractTemplate contains FunctionSignature
# FunctionSignature consist of FunctionParameter representing each parameter in it's signature

def getParamSequenceSize(paramSequence, estimate):
    total = 0
    pointers = 0
    for param in paramSequence:
        if param == "win:Int64":
            total += 8
        elif param == "win:ULong":
            total += 4
        elif param == "GUID":
            total += 16
        elif param == "win:Double":
            total += 8
        elif param == "win:Int32":
            total += 4
        elif param == "win:Boolean":
            total += 4
        elif param == "win:UInt64":
            total += 8
        elif param == "win:UInt32":
            total += 4
        elif param == "win:UInt16":
            total += 2
        elif param == "win:UInt8":
            total += 1
        elif param == "win:Pointer":
            if estimate:
                total += 8
            else:
                pointers += 1
        elif param == "win:Binary":
            total += 1
        elif estimate:
            if param == "win:AnsiString":
                total += 32
            elif param == "win:UnicodeString":
                total += 64
            elif param == "win:Struct":
                total += 32
        else:
            raise Exception("Don't know size for " + param)

    if estimate:
        return total

    return total, pointers


class Template:
    def __repr__(self):
        return "<Template " + self.name + ">"

    def __init__(self, templateName, fnPrototypes, dependencies, structSizes, arrays):
        self.name = templateName
        self.signature = FunctionSignature()
        self.structs = structSizes
        self.arrays = arrays

        for variable in fnPrototypes.paramlist:
            for dependency in dependencies[variable]:
                if not self.signature.getParam(dependency):
                    self.signature.append(dependency, fnPrototypes.getParam(dependency))

    def getFnParam(self, name):
        return self.signature.getParam(name)

    @property
    def num_params(self):
        return len(self.signature.paramlist)

    @property
    def estimated_size(self):
        total = getParamSequenceSize((self.getFnParam(paramName).winType for paramName in self.signature.paramlist), True)

        if total < 32:
            total = 32
        elif total > 1024:
            total = 1024

        return total



class FunctionSignature:
    def __repr__(self):
        return ", ".join(self.paramlist)

    def __init__(self):
        self.LUT       = {} # dictionary of FunctionParameter
        self.paramlist = [] # list of parameters to maintain their order in signature

    def append(self,variable,fnparam):
        self.LUT[variable] = fnparam
        self.paramlist.append(variable)

    def getParam(self,variable):
        return self.LUT.get(variable)

    def getLength(self):
        return len(self.paramlist)

class FunctionParameter:
    def __repr__(self):
        return self.name

    def __init__(self,winType,name,count,prop):
        self.winType  = winType   #ETW type as given in the manifest
        self.name     = name      #parameter name as given in the manifest
        self.prop     = prop      #any special property as determined by the manifest and developer
        #self.count               #indicates if the parameter is a pointer
        if  count == "win:null":
            self.count    = "win:null"
        elif count or winType == "win:GUID" or count == "win:count":
        #special case for GUIDS, consider them as structs
            self.count    = "win:count"
        else:
            self.count    = "win:null"


def getTopLevelElementsByTagName(node,tag):
    dataNodes = []
    for element in node.getElementsByTagName(tag):
        if element.parentNode == node:
            dataNodes.append(element)

    return dataNodes

ignoredXmlTemplateAttribes = frozenset(["map","outType"])
usedXmlTemplateAttribes    = frozenset(["name","inType","count", "length"])

def parseTemplateNodes(templateNodes):

    #return values
    allTemplates           = {}

    for templateNode in templateNodes:
        structCounts = {}
        arrays = {}
        templateName    = templateNode.getAttribute('tid')
        var_Dependecies = {}
        fnPrototypes    = FunctionSignature()
        dataNodes       = getTopLevelElementsByTagName(templateNode,'data')

        # Validate that no new attributes has been added to manifest
        for dataNode in dataNodes:
            nodeMap = dataNode.attributes
            for attrib in nodeMap.values():
                attrib_name = attrib.name
                if attrib_name not in ignoredXmlTemplateAttribes and attrib_name not in usedXmlTemplateAttribes:
                    raise ValueError('unknown attribute: '+ attrib_name + ' in template:'+ templateName)

        for dataNode in dataNodes:
            variable = dataNode.getAttribute('name')
            wintype = dataNode.getAttribute('inType')

            #count and length are the same
            wincount  = dataNode.getAttribute('count')
            winlength = dataNode.getAttribute('length');

            var_Props = None
            var_dependency = [variable]
            if  winlength:
                if wincount:
                    raise Exception("both count and length property found on: " + variable + "in template: " + templateName)
                wincount = winlength

            if (wincount.isdigit() and int(wincount) ==1):
                wincount = ''

            if  wincount:
                if (wincount.isdigit()):
                    var_Props = wincount
                elif  fnPrototypes.getParam(wincount):
                    var_Props = wincount
                    var_dependency.insert(0, wincount)
                    arrays[variable] = wincount

            #construct the function signature

            if  wintype == "win:GUID":
                var_Props = "sizeof(GUID)/sizeof(int)"

            var_Dependecies[variable] = var_dependency
            fnparam        = FunctionParameter(wintype,variable,wincount,var_Props)
            fnPrototypes.append(variable,fnparam)

        structNodes = getTopLevelElementsByTagName(templateNode,'struct')

        for structToBeMarshalled in structNodes:
            structName   = structToBeMarshalled.getAttribute('name')
            countVarName = structToBeMarshalled.getAttribute('count')

            assert(countVarName == "Count")
            assert(countVarName in fnPrototypes.paramlist)
            if not countVarName:
                raise ValueError("Struct '%s' in template '%s' does not have an attribute count." % (structName, templateName))
            
            names = [x.attributes['name'].value for x in structToBeMarshalled.getElementsByTagName("data")]
            types = [x.attributes['inType'].value for x in structToBeMarshalled.getElementsByTagName("data")]

            structCounts[structName] = countVarName
            var_Dependecies[structName] = [countVarName, structName]
            fnparam_pointer = FunctionParameter("win:Struct", structName, "win:count", countVarName)
            fnPrototypes.append(structName, fnparam_pointer)

        allTemplates[templateName] = Template(templateName, fnPrototypes, var_Dependecies, structCounts, arrays)

    return allTemplates

def generateClrallEvents(eventNodes,allTemplates):
    clrallEvents = []
    for eventNode in eventNodes:
        eventName    = eventNode.getAttribute('symbol')
        templateName = eventNode.getAttribute('template')

        #generate EventEnabled
        clrallEvents.append("inline BOOL EventEnabled")
        clrallEvents.append(eventName)
        clrallEvents.append("() {return ")
        clrallEvents.append("EventPipeEventEnabled" + eventName + "() || ")
        clrallEvents.append("(XplatEventLogger::IsEventLoggingEnabled() && EventXplatEnabled")
        clrallEvents.append(eventName+"());}\n\n")
        #generate FireEtw functions
        fnptype     = []
        fnbody      = []
        fnptype.append("inline ULONG FireEtw")
        fnptype.append(eventName)
        fnptype.append("(\n")

        line        = []
        fnptypeline = []

        if templateName:
            template = allTemplates[templateName]
            fnSig = template.signature

            for params in fnSig.paramlist:
                fnparam     = fnSig.getParam(params)
                wintypeName = fnparam.winType
                typewName   = palDataTypeMapping[wintypeName]
                winCount    = fnparam.count
                countw      = palDataTypeMapping[winCount]
                 
                
                if params in template.structs:
                    fnptypeline.append("%sint %s_ElementSize,\n" % (lindent, params))

                fnptypeline.append(lindent)
                fnptypeline.append(typewName)
                fnptypeline.append(countw)
                fnptypeline.append(" ")
                fnptypeline.append(fnparam.name)
                fnptypeline.append(",\n")

            #fnsignature
            for params in fnSig.paramlist:
                fnparam     = fnSig.getParam(params)

                if params in template.structs:                
                    line.append(fnparam.name + "_ElementSize")
                    line.append(", ")

                line.append(fnparam.name)
                line.append(",")

            #remove trailing commas
            if len(line) > 0:
                del line[-1]
            if len(fnptypeline) > 0:
                del fnptypeline[-1]

        fnptype.extend(fnptypeline)
        fnptype.append("\n)\n{\n")
        fnbody.append(lindent)
        fnbody.append("ULONG status = EventPipeWriteEvent" + eventName + "(" + ''.join(line) + ");\n")
        fnbody.append(lindent)
        fnbody.append("if(XplatEventLogger::IsEventLoggingEnabled())\n")
        fnbody.append(lindent)
        fnbody.append("{\n")
        fnbody.append(lindent)
        fnbody.append(lindent)
        fnbody.append("status &= FireEtXplat")
        fnbody.append(eventName)
        fnbody.append("(")
        fnbody.extend(line)
        fnbody.append(");\n")
        fnbody.append(lindent)
        fnbody.append("}\n")
        fnbody.append(lindent)
        fnbody.append("return status;\n")
        fnbody.append("}\n\n")

        clrallEvents.extend(fnptype)
        clrallEvents.extend(fnbody)

    return ''.join(clrallEvents)

def generateClrXplatEvents(eventNodes, allTemplates):
    clrallEvents = []
    for eventNode in eventNodes:
        eventName    = eventNode.getAttribute('symbol')
        templateName = eventNode.getAttribute('template')

        #generate EventEnabled
        clrallEvents.append("extern \"C\" BOOL EventXplatEnabled")
        clrallEvents.append(eventName)
        clrallEvents.append("();\n")
        #generate FireEtw functions
        fnptype     = []
        fnptypeline = []
        fnptype.append("extern \"C\" ULONG   FireEtXplat")
        fnptype.append(eventName)
        fnptype.append("(\n")

        if templateName:
            template = allTemplates[templateName]
            fnSig = template.signature

            for params in fnSig.paramlist:
                fnparam     = fnSig.getParam(params)
                wintypeName = fnparam.winType
                typewName   = palDataTypeMapping[wintypeName]
                winCount    = fnparam.count
                countw      = palDataTypeMapping[winCount]

                
                if params in template.structs:
                    fnptypeline.append("%sint %s_ElementSize,\n" % (lindent, params))

                fnptypeline.append(lindent)
                fnptypeline.append(typewName)
                fnptypeline.append(countw)
                fnptypeline.append(" ")
                fnptypeline.append(fnparam.name)
                fnptypeline.append(",\n")

            #remove trailing commas
            if len(fnptypeline) > 0:
                del fnptypeline[-1]

        fnptype.extend(fnptypeline)
        fnptype.append("\n);\n")
        clrallEvents.extend(fnptype)

    return ''.join(clrallEvents)

def generateClrEventPipeWriteEvents(eventNodes, allTemplates):
    clrallEvents = []
    for eventNode in eventNodes:
        eventName    = eventNode.getAttribute('symbol')
        templateName = eventNode.getAttribute('template')

        #generate EventPipeEventEnabled and EventPipeWriteEvent functions
        eventenabled = []
        writeevent   = []
        fnptypeline  = []

        eventenabled.append("extern \"C\" bool EventPipeEventEnabled")
        eventenabled.append(eventName)
        eventenabled.append("();\n")

        writeevent.append("extern \"C\" ULONG EventPipeWriteEvent")
        writeevent.append(eventName)
        writeevent.append("(\n")

        if templateName:
            template = allTemplates[templateName]
            fnSig    = template.signature

            for params in fnSig.paramlist:
                fnparam     = fnSig.getParam(params)
                wintypeName = fnparam.winType
                typewName   = palDataTypeMapping[wintypeName]
                winCount    = fnparam.count
                countw      = palDataTypeMapping[winCount]

                if params in template.structs:
                    fnptypeline.append("%sint %s_ElementSize,\n" % (lindent, params))

                fnptypeline.append(lindent)
                fnptypeline.append(typewName)
                fnptypeline.append(countw)
                fnptypeline.append(" ")
                fnptypeline.append(fnparam.name)
                fnptypeline.append(",\n")

            #remove trailing commas
            if len(fnptypeline) > 0:
                del fnptypeline[-1]

        writeevent.extend(fnptypeline)
        writeevent.append("\n);\n")
        clrallEvents.extend(eventenabled)
        clrallEvents.extend(writeevent)

    return ''.join(clrallEvents)

#generates the dummy header file which is used by the VM as entry point to the logging Functions
def generateclrEtwDummy(eventNodes,allTemplates):
    clretmEvents = []
    for eventNode in eventNodes:
        eventName    = eventNode.getAttribute('symbol')
        templateName = eventNode.getAttribute('template')

        fnptype     = []
        #generate FireEtw functions
        fnptype.append("#define FireEtw")
        fnptype.append(eventName)
        fnptype.append("(");
        line        = []
        if templateName:
            template = allTemplates[templateName]
            fnSig = template.signature

            for params in fnSig.paramlist:
                fnparam     = fnSig.getParam(params)

                if params in template.structs:
                    line.append(fnparam.name + "_ElementSize")
                    line.append(", ")

                line.append(fnparam.name)
                line.append(", ")

            #remove trailing commas
            if len(line) > 0:
                del line[-1]

        fnptype.extend(line)
        fnptype.append(") 0\n")
        clretmEvents.extend(fnptype)

    return ''.join(clretmEvents)

def generateClralltestEvents(sClrEtwAllMan):
    tree           = DOM.parse(sClrEtwAllMan)

    clrtestEvents = []
    for providerNode in tree.getElementsByTagName('provider'):
        templateNodes = providerNode.getElementsByTagName('template')
        allTemplates  = parseTemplateNodes(templateNodes)
        eventNodes = providerNode.getElementsByTagName('event')
        for eventNode in eventNodes:
            eventName    = eventNode.getAttribute('symbol')
            templateName = eventNode.getAttribute('template')
            clrtestEvents.append(" EventXplatEnabled" + eventName + "();\n")
            clrtestEvents.append("Error |= FireEtXplat" + eventName + "(\n")

            line =[]
            if templateName:
                template = allTemplates[templateName]
                fnSig = template.signature

                for params in fnSig.paramlist:
                    if params in template.structs:
                        line.append("sizeof(Struct1),\n")

                    argline =''
                    fnparam     = fnSig.getParam(params)
                    if fnparam.name.lower() == 'count':
                        argline = '2'
                    else:
                        if fnparam.winType == "win:Binary":
                            argline = 'win_Binary'
                        elif fnparam.winType == "win:Pointer" and fnparam.count == "win:count":
                            argline = "(const void**)&var11"
                        elif fnparam.winType == "win:Pointer" :
                            argline = "(const void*)var11"
                        elif fnparam.winType =="win:AnsiString":
                            argline    = '" Testing AniString "'
                        elif fnparam.winType =="win:UnicodeString":
                            argline    = 'W(" Testing UnicodeString ")'
                        else:
                            if fnparam.count == "win:count":
                                line.append("&")

                            argline = fnparam.winType.replace(":","_")

                    line.append(argline)
                    line.append(",\n")

                #remove trailing commas
                if len(line) > 0:
                    del line[-1]
                    line.append("\n")
            line.append(");\n")
            clrtestEvents.extend(line)

    return ''.join(clrtestEvents)

def generateSanityTest(sClrEtwAllMan,testDir):

    if not testDir:
        return
    print('Generating Event Logging Tests')

    if not os.path.exists(testDir):
        os.makedirs(testDir)

    cmake_file = testDir + "/CMakeLists.txt"
    test_cpp   = "clralltestevents.cpp"
    testinfo   = testDir + "/testinfo.dat"
    Cmake_file = open(cmake_file,'w')
    Test_cpp   = open(testDir + "/" + test_cpp,'w')
    Testinfo   = open(testinfo,'w')

    #CMake File:
    Cmake_file.write(stdprolog_cmake)
    Cmake_file.write("""
    cmake_minimum_required(VERSION 2.8.12.2)
    set(CMAKE_INCLUDE_CURRENT_DIR ON)
    set(SOURCES
    """)
    Cmake_file.write(test_cpp)
    Cmake_file.write("""
        )
    include_directories(${GENERATED_INCLUDE_DIR})
    include_directories(${COREPAL_SOURCE_DIR}/inc/rt)

    add_executable(eventprovidertest
                  ${SOURCES}
                   )
    set(EVENT_PROVIDER_DEPENDENCIES "")
    set(EVENT_PROVIDER_LINKER_OTPTIONS "")
    if(FEATURE_EVENT_TRACE)
        add_definitions(-DFEATURE_EVENT_TRACE=1)
            list(APPEND EVENT_PROVIDER_DEPENDENCIES
                 coreclrtraceptprovider
                 eventprovider
                 )
            list(APPEND EVENT_PROVIDER_LINKER_OTPTIONS
                 ${EVENT_PROVIDER_DEPENDENCIES}
                 )

    endif(FEATURE_EVENT_TRACE)

    add_dependencies(eventprovidertest  ${EVENT_PROVIDER_DEPENDENCIES} coreclrpal)
    target_link_libraries(eventprovidertest
                          coreclrpal
                          ${EVENT_PROVIDER_LINKER_OTPTIONS}
                          )
    """)
    Testinfo.write("""
 Copyright (c) Microsoft Corporation.  All rights reserved.
 #

 Version = 1.0
 Section = EventProvider
 Function = EventProvider
 Name = PAL test for FireEtW* and EventEnabled* functions
 TYPE = DEFAULT
 EXE1 = eventprovidertest
 Description
 =This is a sanity test to check that there are no crashes in Xplat eventing
    """)

    #Test.cpp
    Test_cpp.write(stdprolog)
    Test_cpp.write("""
/*=====================================================================
**
** Source:   clralltestevents.cpp
**
** Purpose:  Ensure Correctness of Eventing code
**
**
**===================================================================*/
#include <palsuite.h>
#include <clrxplatevents.h>

typedef struct _Struct1 {
                ULONG   Data1;
                unsigned short Data2;
                unsigned short Data3;
                unsigned char  Data4[8];
} Struct1;

Struct1 var21[2] = { { 245, 13, 14, "deadbea" }, { 542, 0, 14, "deadflu" } };

Struct1* var11 = var21;
Struct1* win_Struct = var21;

GUID win_GUID ={ 245, 13, 14, "deadbea" };
double win_Double =34.04;
ULONG win_ULong = 34;
BOOL win_Boolean = FALSE;
unsigned __int64 win_UInt64 = 114;
unsigned int win_UInt32 = 4;
unsigned short win_UInt16 = 12;
unsigned char win_UInt8 = 9;
int win_Int32 = 12;
BYTE* win_Binary =(BYTE*)var21 ;
int __cdecl main(int argc, char **argv)
{

            /* Initialize the PAL.
            */

            if(0 != PAL_Initialize(argc, argv))
            {
               return FAIL;
            }

            ULONG Error = ERROR_SUCCESS;
#if defined(FEATURE_EVENT_TRACE)
            Trace("\\n Starting functional  eventing APIs tests  \\n");
""")

    Test_cpp.write(generateClralltestEvents(sClrEtwAllMan))
    Test_cpp.write("""
/* Shutdown the PAL.
 */

         if (Error != ERROR_SUCCESS)
         {
             Fail("One or more eventing Apis failed\\n ");
             return FAIL;
          }
          Trace("\\n All eventing APIs were fired succesfully \\n");
#endif //defined(FEATURE_EVENT_TRACE)
          PAL_Terminate();
          return PASS;
                                 }

""")
    Cmake_file.close()
    Test_cpp.close()
    Testinfo.close()

def generateEtmDummyHeader(sClrEtwAllMan,clretwdummy):

    if not clretwdummy:
        return

    print(' Generating Dummy Event Headers')
    tree           = DOM.parse(sClrEtwAllMan)

    incDir = os.path.dirname(os.path.realpath(clretwdummy))
    if not os.path.exists(incDir):
        os.makedirs(incDir)

    Clretwdummy    = open(clretwdummy,'w')
    Clretwdummy.write(stdprolog + "\n")

    for providerNode in tree.getElementsByTagName('provider'):
        templateNodes = providerNode.getElementsByTagName('template')
        allTemplates  = parseTemplateNodes(templateNodes)
        eventNodes = providerNode.getElementsByTagName('event')
        #pal: create etmdummy.h
        Clretwdummy.write(generateclrEtwDummy(eventNodes, allTemplates) + "\n")

    Clretwdummy.close()

def generatePlformIndependentFiles(sClrEtwAllMan,incDir,etmDummyFile):

    generateEtmDummyHeader(sClrEtwAllMan,etmDummyFile)
    tree           = DOM.parse(sClrEtwAllMan)

    if not incDir:
        return

    print(' Generating Event Headers')
    if not os.path.exists(incDir):
        os.makedirs(incDir)

    clrallevents   = incDir + "/clretwallmain.h"
    clrxplatevents = incDir + "/clrxplatevents.h"
    clreventpipewriteevents = incDir + "/clreventpipewriteevents.h"

    Clrallevents   = open(clrallevents,'w')
    Clrxplatevents = open(clrxplatevents,'w')
    Clreventpipewriteevents = open(clreventpipewriteevents,'w')

    Clrallevents.write(stdprolog + "\n")
    Clrxplatevents.write(stdprolog + "\n")
    Clreventpipewriteevents.write(stdprolog + "\n")

    Clrallevents.write("\n#include \"clrxplatevents.h\"\n")
    Clrallevents.write("#include \"clreventpipewriteevents.h\"\n\n")
    
    for providerNode in tree.getElementsByTagName('provider'):
        templateNodes = providerNode.getElementsByTagName('template')
        allTemplates  = parseTemplateNodes(templateNodes)
        eventNodes = providerNode.getElementsByTagName('event')
        #vm header:
        Clrallevents.write(generateClrallEvents(eventNodes, allTemplates) + "\n")

        #pal: create clrallevents.h
        Clrxplatevents.write(generateClrXplatEvents(eventNodes, allTemplates) + "\n")

        #eventpipe: create clreventpipewriteevents.h
        Clreventpipewriteevents.write(generateClrEventPipeWriteEvents(eventNodes, allTemplates) + "\n")

    Clrxplatevents.close()
    Clrallevents.close()
    Clreventpipewriteevents.close()

class EventExclusions:
    def __init__(self):
        self.nostack         = set()
        self.explicitstack   = set()
        self.noclrinstance   = set()

def parseExclusionList(exclusionListFile):
    ExclusionFile   = open(exclusionListFile,'r')
    exclusionInfo   = EventExclusions()

    for line in ExclusionFile:
        line = line.strip()

        #remove comments
        if not line or line.startswith('#'):
            continue

        tokens = line.split(':')
        #entries starting with nomac are ignored
        if "nomac" in tokens:
            continue

        if len(tokens) > 5:
            raise Exception("Invalid Entry " + line + "in "+ exclusionListFile)

        eventProvider = tokens[2]
        eventTask     = tokens[1]
        eventSymbol   = tokens[4]

        if eventProvider == '':
            eventProvider = "*"
        if eventTask     == '':
            eventTask     = "*"
        if eventSymbol   == '':
            eventSymbol   = "*"
        entry = eventProvider + ":" + eventTask + ":" + eventSymbol

        if tokens[0].lower() == "nostack":
            exclusionInfo.nostack.add(entry)
        if tokens[0].lower() == "stack":
            exclusionInfo.explicitstack.add(entry)
        if tokens[0].lower() == "noclrinstanceid":
            exclusionInfo.noclrinstance.add(entry)
    ExclusionFile.close()

    return exclusionInfo

def getStackWalkBit(eventProvider, taskName, eventSymbol, stackSet):
    for entry in stackSet:
        tokens = entry.split(':')

        if len(tokens) != 3:
            raise Exception("Error, possible error in the script which introduced the enrty "+ entry)

        eventCond  = tokens[0] == eventProvider or tokens[0] == "*"
        taskCond   = tokens[1] == taskName      or tokens[1] == "*"
        symbolCond = tokens[2] == eventSymbol   or tokens[2] == "*"

        if eventCond and taskCond and symbolCond:
            return False
    return True

#Add the miscelaneous checks here
def checkConsistency(sClrEtwAllMan,exclusionListFile):
    tree                      = DOM.parse(sClrEtwAllMan)
    exclusionInfo = parseExclusionList(exclusionListFile)
    for providerNode in tree.getElementsByTagName('provider'):

        stackSupportSpecified = {}
        eventNodes            = providerNode.getElementsByTagName('event')
        templateNodes         = providerNode.getElementsByTagName('template')
        eventProvider         = providerNode.getAttribute('name')
        allTemplates          = parseTemplateNodes(templateNodes)

        for eventNode in eventNodes:
            taskName         = eventNode.getAttribute('task')
            eventSymbol      = eventNode.getAttribute('symbol')
            eventTemplate    = eventNode.getAttribute('template')
            eventValue       = int(eventNode.getAttribute('value'))
            clrInstanceBit   = getStackWalkBit(eventProvider, taskName, eventSymbol, exclusionInfo.noclrinstance)
            sLookupFieldName = "ClrInstanceID"
            sLookupFieldType = "win:UInt16"

            if clrInstanceBit and allTemplates.get(eventTemplate):
                # check for the event template and look for a field named ClrInstanceId of type win:UInt16
                fnParam = allTemplates[eventTemplate].getFnParam(sLookupFieldName)

                if not(fnParam and fnParam.winType == sLookupFieldType):
                    raise Exception(exclusionListFile + ":No " + sLookupFieldName + " field of type " + sLookupFieldType + " for event symbol " +  eventSymbol)

            # If some versions of an event are on the nostack/stack lists,
            # and some versions are not on either the nostack or stack list,
            # then developer likely forgot to specify one of the versions

            eventStackBitFromNoStackList       = getStackWalkBit(eventProvider, taskName, eventSymbol, exclusionInfo.nostack)
            eventStackBitFromExplicitStackList = getStackWalkBit(eventProvider, taskName, eventSymbol, exclusionInfo.explicitstack)
            sStackSpecificityError = exclusionListFile + ": Error processing event :" + eventSymbol + "(ID" + str(eventValue) + "): This file must contain either ALL versions of this event or NO versions of this event. Currently some, but not all, versions of this event are present\n"

            if not stackSupportSpecified.get(eventValue):
                 # Haven't checked this event before.  Remember whether a preference is stated
                if ( not eventStackBitFromNoStackList) or ( not eventStackBitFromExplicitStackList):
                    stackSupportSpecified[eventValue] = True
                else:
                    stackSupportSpecified[eventValue] = False
            else:
                # We've checked this event before.
                if stackSupportSpecified[eventValue]:
                    # When we last checked, a preference was previously specified, so it better be specified here
                    if eventStackBitFromNoStackList and eventStackBitFromExplicitStackList:
                        raise Exception(sStackSpecificityError)
                else:
                    # When we last checked, a preference was not previously specified, so it better not be specified here
                    if ( not eventStackBitFromNoStackList) or ( not eventStackBitFromExplicitStackList):
                        raise Exception(sStackSpecificityError)
import argparse
import sys

def main(argv):

    #parse the command line
    parser = argparse.ArgumentParser(description="Generates the Code required to instrument LTTtng logging mechanism")

    required = parser.add_argument_group('required arguments')
    required.add_argument('--man',  type=str, required=True,
                                    help='full path to manifest containig the description of events')
    required.add_argument('--exc',  type=str, required=True,
                                    help='full path to exclusion list')
    required.add_argument('--inc',  type=str, default=None,
                                    help='full path to directory where the header files will be generated')
    required.add_argument('--dummy',  type=str,default=None,
                                    help='full path to file that will have dummy definitions of FireEtw functions')
    required.add_argument('--testdir',  type=str, default=None,
                                    help='full path to directory where the test assets will be deployed' )
    args, unknown = parser.parse_known_args(argv)
    if unknown:
        print('Unknown argument(s): ', ', '.join(unknown))
        return const.UnknownArguments

    sClrEtwAllMan     = args.man
    exclusionListFile = args.exc
    incdir            = args.inc
    etmDummyFile      = args.dummy
    testDir           = args.testdir

    checkConsistency(sClrEtwAllMan, exclusionListFile)
    generatePlformIndependentFiles(sClrEtwAllMan,incdir,etmDummyFile)
    generateSanityTest(sClrEtwAllMan,testDir)
if __name__ == '__main__':
    return_code = main(sys.argv[1:])
    sys.exit(return_code)
